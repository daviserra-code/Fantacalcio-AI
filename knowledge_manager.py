import os
import json
import uuid
import time
import shutil
from typing import List, Dict, Any, Optional

from chromadb import PersistentClient
from chromadb.config import Settings

from hf_embedder import HFEmbedder


def _sanitize_meta(meta: dict) -> dict:
    """Sanifica metadati per Chroma: solo str|int|float|bool, None -> ''."""
    out = {}
    for k, v in (meta or {}).items():
        if v is None:
            out[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


class KnowledgeManager:
    """
    Gestisce la persistenza su Chroma e l'ingest dei documenti usando
    lo stesso modello di embedding del RAG (HFEmbedder).
    Se Chroma lancia errori di compatibilita' (es. '_type'), fa backup e ricrea il DB.
    """

    def __init__(self, collection_name: str = "fantacalcio_knowledge"):
        # Path e nome collection stabili (niente timestamp)
        self.db_path = os.environ.get("CHROMA_DB", "./chroma_db")
        os.makedirs(self.db_path, exist_ok=True)

        self.collection_name = os.environ.get("CHROMA_COLLECTION", collection_name)

        def _new_client(path: str) -> PersistentClient:
            # disabilita telemetria per meno rumore
            return PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))

        # 1) prova ad aprire e listare le collections per forzare la lettura del sysdb
        try:
            self.client = _new_client(self.db_path)
            _ = self.client.list_collections()  # se il sysdb e' corrotto, esplode qui
        except Exception as e:
            # 2) autoriparazione: sposta il vecchio DB in backup e ricrea cartella pulita
            print(f"[KM] Chroma sysdb incompatibile/corrotto: {e}")
            backup_path = f"{self.db_path}_backup_{int(time.time())}"
            try:
                shutil.move(self.db_path, backup_path)
                print(f"[KM] Vecchio DB spostato in: {backup_path}")
            except Exception as e2:
                print(f"[KM] Backup fallito: {e2}")
            os.makedirs(self.db_path, exist_ok=True)
            self.client = _new_client(self.db_path)

        # 3) carica o crea la collection stabile
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # 4) embedder condiviso con il RAG
        self.embedder = HFEmbedder()

    # ---------------------------
    # Utils
    # ---------------------------
    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0

    # ---------------------------
    # Ingest
    # ---------------------------
    def add_knowledge(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """
        Aggiunge un singolo documento con embedding pre-calcolato (HFEmbedder).
        """
        if not text:
            return doc_id or str(uuid.uuid4())

        _id = doc_id or str(uuid.uuid4())
        md = _sanitize_meta(metadata or {})

        # embedding "passage" (non query)
        emb = self.embedder.embed_one(text, is_query=False).tolist()

        self.collection.add(
            ids=[_id],
            documents=[text],
            metadatas=[md],
            embeddings=[emb],
        )
        return _id

    def add_many(
        self,
        items: List[Dict[str, Any]],
        batch_size: int = 64,
    ) -> Dict[str, int]:
        """
        Ingest in batch: items = [{id?, text, metadata?}, ...]
        """
        texts, metas, ids = [], [], []
        for it in items:
            t = (it.get("text") or "").strip()
            if not t:
                continue
            texts.append(t)
            metas.append(_sanitize_meta(it.get("metadata") or {}))  # SANITIZZA
            ids.append(it.get("id") or str(uuid.uuid4()))

        added, i = 0, 0
        while i < len(texts):
            b_t = texts[i : i + batch_size]
            b_m = metas[i : i + batch_size]
            b_i = ids[i : i + batch_size]

            embs = self.embedder.embed_texts(b_t, is_query=False).tolist()
            self.collection.add(
                ids=b_i,
                documents=b_t,
                metadatas=b_m,
                embeddings=embs,
            )
            added += len(b_t)
            i += batch_size

        return {"added": added, "failed": 0}

    # ---------------------------
    # Retrieval semplice (se serve fuori dal RAG)
    # ---------------------------
    def search_knowledge(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Ricerca su Chroma con embedding della query via HFEmbedder.
        Ritorna [{text, metadata, distance, similarity}, ...]
        """
        if not query:
            return []
        q = self.embedder.embed_one(query, is_query=True).tolist()
        res = self.collection.query(
            query_embeddings=[q],
            n_results=max(1, n_results),
            include=["documents", "metadatas", "distances"],
        )
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        out = []
        for i in range(len(docs)):
            dist = float(dists[i]) if dists and i < len(dists) else None
            sim = (1.0 - dist) if (dist is not None) else None  # approx per cosine
            out.append(
                {
                    "text": docs[i],
                    "metadata": metas[i],
                    "distance": dist,
                    "cosine_similarity": sim,
                    "relevance_score": sim if sim is not None else 0.0,
                }
            )
        return out

    # ---------------------------
    # Import da JSONL (compat)
    # ---------------------------
    def load_from_jsonl(self, jsonl_path: str) -> int:
        """
        Carica da un JSONL con righe del tipo:
        {"id": "...", "text": "...", "metadata": {...}}
        """
        if not os.path.exists(jsonl_path):
            print(f"[KM] JSONL non trovato: {jsonl_path}")
            return 0

        items = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    t = data.get("text") or ""
                    if not t:
                        continue
                    items.append(
                        {
                            "id": data.get("id"),
                            "text": t,
                            "metadata": data.get("metadata") or {},
                        }
                    )
                except json.JSONDecodeError:
                    continue

        stats = self.add_many(items)
        print(f"[KM] Caricati {stats['added']} documenti da {jsonl_path}")
        return stats["added"]

    # ---------------------------
    # Reset / rebuild
    # ---------------------------
    def reset_database(self) -> bool:
        """
        Svuota tutto il DB e ricrea la stessa collection vuota.
        """
        try:
            self.client.reset()
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            print(f"[KM] Reset DB completato. Collection: {self.collection_name}")
            return True
        except Exception as e:
            print(f"[KM] Errore reset DB: {e}")
            return False

    def rebuild_database_from_jsonl(self, jsonl_files: List[str]) -> int:
        """
        Reset + ingest da una lista di file JSONL.
        """
        total = 0
        if self.reset_database():
            for p in jsonl_files:
                total += self.load_from_jsonl(p)
        print(f"[KM] Rebuild completato. Totale ingest: {total}")
        return total
import os
import json
import time
import uuid
from typing import List, Dict, Any, Optional

import chromadb
from sentence_transformers import SentenceTransformer


def _env_true(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "y", "on")


class KnowledgeManager:
    """
    Gestione KB con Chroma + SentenceTransformer.
    - Auto-ripara collezioni corrotte
    - Supporta upsert (se disponibile) o add "safe" senza duplicati
    - Sanitizza i metadati per compatibilità Chroma
    - Guard opzionale per bloccare scritture durante le richieste (ALLOW_KB_WRITES)
    """

    def __init__(
        self,
        collection_name: str = "fantacalcio_knowledge",
        persist_path: str = "./chroma_db",
        embed_model: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
    ):
        self.collection_name = collection_name
        self.persist_path = persist_path
        self.embed_model_name = embed_model
        self.device = device

        # Flag: consenti scritture su KB? (puoi settare ALLOW_KB_WRITES=false in prod)
        self.allow_writes = _env_true("ALLOW_KB_WRITES", "true")

        # Embedder (con retry)
        self.embedding_model: Optional[SentenceTransformer] = None
        self._init_embedder()

        # Client/Collection (con autoriparazione)
        self.client = chromadb.PersistentClient(path=self.persist_path)
        self.collection = self._init_collection()

    # ---------- INIT HELPERS ----------

    def _init_embedder(self, max_attempts: int = 10):
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                print(f"🔄 Initializing SentenceTransformer (attempt {attempt}/{max_attempts})...")
                self.embedding_model = SentenceTransformer(self.embed_model_name, device=self.device)
                # test veloce
                _ = self.embedding_model.encode("fantacalcio", show_progress_bar=False)
                print("✅ SentenceTransformer initialized successfully on attempt", attempt)
                return
            except Exception as e:
                last_err = e
                time.sleep(0.6)
        raise RuntimeError(f"Impossibile inizializzare SentenceTransformer: {last_err}")

    def _init_collection(self):
        # 1) prova a caricare
        try:
            col = self.client.get_collection(self.collection_name)
            _ = col.count()
            return col
        except Exception as e:
            print(f"⚠️ Could not load existing collection '{self.collection_name}': {e}")

        # 2) crea nuova
        try:
            col = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Fantacalcio knowledge base for RAG"}
            )
            return col
        except Exception as e:
            print(f"⚠️ Could not create collection '{self.collection_name}': {e}")

        # 3) reset client e riprova
        try:
            print("🔄 Resetting ChromaDB client...")
            self.client.reset()
            col = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Fantacalcio knowledge base for RAG"}
            )
            return col
        except Exception as e:
            # 4) fallback nome unico
            print(f"⚠️ Reset strategy failed: {e}")
            unique = f"{self.collection_name}_{int(time.time())}"
            col = self.client.create_collection(name=unique)
            self.collection_name = unique
            print(f"✅ Created fallback collection: {unique}")
            return col

    # ---------- META / UTILS ----------

    @staticmethod
    def _sanitize_meta(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in (meta or {}).items():
            if v is None:
                out[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                out[k] = v
            else:
                out[k] = str(v)
        return out

    def _encode(self, texts: List[str]) -> List[List[float]]:
        return self.embedding_model.encode(texts, show_progress_bar=False).tolist()

    # ---------- ADD / UPSERT (con guard scrittura) ----------

    def _safe_add(self, ids: List[str], embeddings: List[List[float]], documents: List[str], metadatas: List[Dict[str, Any]]):
        """Aggiunge ignorando ID già presenti."""
        if not self.allow_writes:
            # blocco scritture se disabilitate
            return

        existing = set()
        try:
            got = self.collection.get(ids=ids, include=[])
            for _id in (got.get("ids") or []):
                existing.add(_id)
        except Exception:
            # alcune versioni di Chroma possono alzare eccezione se gli id non esistono
            pass

        new_ids, new_emb, new_docs, new_meta = [], [], [], []
        for i, _id in enumerate(ids):
            if _id in existing:
                continue
            new_ids.append(_id)
            new_emb.append(embeddings[i])
            new_docs.append(documents[i])
            new_meta.append(metadatas[i])

        if new_ids:
            self.collection.add(
                ids=new_ids,
                embeddings=new_emb,
                documents=new_docs,
                metadatas=new_meta
            )

    def add_knowledge(self, text: str, metadata: Optional[Dict[str, Any]] = None, doc_id: Optional[str] = None) -> str:
        if not self.allow_writes:
            # se le scritture non sono permesse, non fare nulla (evita warning "Add of existing ...")
            return doc_id or str(uuid.uuid4())

        doc_id = doc_id or str(uuid.uuid4())
        emb = self._encode([text])[0]
        meta = self._sanitize_meta(metadata)

        # upsert se disponibile, altrimenti safe_add
        if hasattr(self.collection, "upsert"):
            self.collection.upsert(
                ids=[doc_id],
                embeddings=[emb],
                documents=[text],
                metadatas=[meta],
            )
        else:
            self._safe_add(
                ids=[doc_id],
                embeddings=[emb],
                documents=[text],
                metadatas=[meta],
            )
        return doc_id

    def add_many(self, items: List[Dict[str, Any]], batch_size: int = 64) -> Dict[str, int]:
        """
        items: [{id, text, metadata}]
        Ritorna {'added': N}
        """
        if not self.allow_writes:
            return {"added": 0}

        added = 0
        buf_ids, buf_docs, buf_meta = [], [], []

        def flush():
            nonlocal added, buf_ids, buf_docs, buf_meta
            if not buf_ids:
                return
            embs = self._encode(buf_docs)

            if hasattr(self.collection, "upsert"):
                self.collection.upsert(
                    ids=buf_ids,
                    embeddings=embs,
                    documents=buf_docs,
                    metadatas=[self._sanitize_meta(m) for m in buf_meta],
                )
                added += len(buf_ids)
            else:
                before = len(buf_ids)
                self._safe_add(
                    ids=buf_ids,
                    embeddings=embs,
                    documents=buf_docs,
                    metadatas=[self._sanitize_meta(m) for m in buf_meta],
                )
                added += before

            buf_ids, buf_docs, buf_meta = [], [], []

        for it in items:
            _id = it.get("id") or str(uuid.uuid4())
            txt = it.get("text") or ""
            meta = it.get("metadata") or {}
            buf_ids.append(_id)
            buf_docs.append(txt)
            buf_meta.append(meta)
            if len(buf_ids) >= batch_size:
                flush()
        flush()
        return {"added": added}

    # ---------- QUERY ----------

    def search_knowledge(self, query: str, n_results: int = 8, where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        q_emb = self._encode([query])[0]
        res = self.collection.query(
            query_embeddings=[q_emb],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
            where=where or {},
        )
        out: List[Dict[str, Any]] = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i in range(len(docs)):
            dist = dists[i]
            sim = 1.0 - dist if dist <= 1.0 else max(0.0, 2 - dist)
            out.append({
                "text": docs[i],
                "metadata": metas[i],
                "distance": dist,
                "cosine_similarity": sim,
                "relevance_score": sim,
            })
        return out

    # ---------- MAINTENANCE ----------

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0

    def reset_database(self) -> bool:
        try:
            self.client.reset()
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Fantacalcio knowledge base for RAG"}
            )
            return True
        except Exception as e:
            print(f"❌ Error resetting database: {e}")
            return False

    # ---------- IMPORT JSONL ----------

    def load_from_jsonl(self, jsonl_path: str) -> int:
        if not self.allow_writes:
            return 0
        if not os.path.exists(jsonl_path):
            print(f"❌ JSONL file not found: {jsonl_path}")
            return 0
        items = []
        added = 0
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line.strip())
                    items.append({
                        "id": row.get("id"),
                        "text": row.get("text", ""),
                        "metadata": row.get("metadata", {}),
                    })
                except Exception as e:
                    print(f"⚠️ JSONL parse error: {e}")
        if items:
            stats = self.add_many(items)
            added = stats.get("added", 0)
        print(f"✅ Loaded {added} entries from {jsonl_path}")
        return added
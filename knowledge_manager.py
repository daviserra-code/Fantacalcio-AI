# knowledge_manager.py
# -*- coding: utf-8 -*-
import os
import json
import time
import uuid
import logging
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def _safe_metadata(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Chroma accetta solo str/int/float/bool per i metadati.
    Converte None in stringa vuota e rimuove tipi non supportati.
    """
    if not meta:
        return {}
    safe: Dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)):
            safe[k] = v
        elif v is None:
            safe[k] = ""
        else:
            # fallback: serializza in stringa breve
            try:
                safe[k] = json.dumps(v)[:512]
            except Exception:
                safe[k] = str(v)[:512]
    return safe


class KnowledgeManager:
    """
    Gestione KB (Chroma + SentenceTransformer) con:
      - inizializzazione resiliente
      - add (singolo e bulk)
      - search_knowledge con patch NO-where quando vuoto
      - caricamento da JSONL
      - creazione contesto per LLM
    """

    def __init__(
        self,
        collection_name: str = "fantacalcio_knowledge",
        chroma_path: str = "./chroma_db",
        embedding_model_name: str = "all-MiniLM-L6-v2",
        query_cache_size: int = 100,
    ) -> None:
        self.collection_name = collection_name
        self.chroma_path = chroma_path
        self.embedding_model_name = embedding_model_name
        self.query_cache_size = query_cache_size

        self.client: Optional[ClientAPI] = None
        self.collection: Optional[Collection] = None
        self.embedding_model: Optional[SentenceTransformer] = None
        self.embedding_disabled: bool = False
        self.query_cache: Dict[str, List[Dict[str, Any]]] = {}

        # 1) Inizializza client Chroma
        self._init_chroma()

        # 2) Inizializza embedding locale
        self._init_embeddings()

        # 3) Recupera o crea collection
        self._init_collection()

        # Log stato iniziale
        try:
            count = self.count()
        except Exception:
            count = 0
        print(f"[RAG] Pipeline inizializzata. Collection='{self.collection_name}', documenti indicizzati: {count}")

    # --------------------------
    # INIT
    # --------------------------
    def _init_chroma(self) -> None:
        os.makedirs(self.chroma_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.chroma_path)

    def _init_embeddings(self) -> None:
        max_attempts = 10
        for attempt in range(1, max_attempts + 1):
            try:
                print(f"🔄 Initializing SentenceTransformer (attempt {attempt}/{max_attempts})...")
                # Ambiente pulito CPU
                os.environ["CUDA_VISIBLE_DEVICES"] = ""
                os.environ["TOKENIZERS_PARALLELISM"] = "false"
                self.embedding_model = SentenceTransformer(self.embedding_model_name, device="cpu")

                # Test rapido
                _ = self.embedding_model.encode("fantacalcio test", show_progress_bar=False)
                print("✅ SentenceTransformer initialized successfully on attempt 1")
                return
            except Exception as e:
                if attempt == max_attempts:
                    logger.error(f"❌ Embedding init failed: {e}")
                    self.embedding_disabled = True
                else:
                    time.sleep(0.6)

    def _init_collection(self) -> None:
        assert self.client is not None
        try:
            self.collection = self.client.get_collection(self.collection_name)
        except Exception:
            # create if not exists
            try:
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Fantacalcio knowledge base for RAG"},
                )
            except Exception as e:
                logger.error(f"❌ Cannot create collection '{self.collection_name}': {e}")
                # fallback name
                fallback = f"{self.collection_name}_{int(time.time())}"
                self.collection = self.client.create_collection(name=fallback)
                self.collection_name = fallback

    # --------------------------
    # UTILS
    # --------------------------
    def _encode(self, text: str) -> List[float]:
        if self.embedding_disabled or self.embedding_model is None:
            raise RuntimeError("Embeddings disabled or model not available.")
        return self.embedding_model.encode(text, show_progress_bar=False).tolist()

    def count(self) -> int:
        return int(self.collection.count()) if self.collection else 0

    # --------------------------
    # ADD / BULK ADD
    # --------------------------
    def add_knowledge(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        if not self.collection:
            raise RuntimeError("Collection not initialized")

        doc_id = doc_id or str(uuid.uuid4())
        try:
            emb = self._encode(text)
            meta = _safe_metadata(metadata)
            self.collection.add(
                ids=[doc_id],
                documents=[text],
                embeddings=[emb],
                metadatas=[meta],
            )
            return doc_id
        except Exception as e:
            logger.warning(f"⚠️ Error adding knowledge '{doc_id}': {e}")
            return doc_id

    def add_bulk(
        self,
        items: List[Dict[str, Any]],
        batch_size: int = 64,
    ) -> int:
        """
        items: [{"text": str, "metadata": dict, "id": optional_str}, ...]
        """
        if not self.collection:
            raise RuntimeError("Collection not initialized")
        if self.embedding_disabled or self.embedding_model is None:
            logger.warning("⚠️ Embeddings disabled: bulk add skipped.")
            return 0

        added = 0
        buf_ids, buf_docs, buf_metas, buf_embs = [], [], [], []

        for it in items:
            text = it.get("text", "")
            if not text:
                continue
            mid = it.get("id") or str(uuid.uuid4())
            meta = _safe_metadata(it.get("metadata", {}))

            try:
                emb = self._encode(text)
            except Exception as e:
                logger.warning(f"⚠️ Embedding failed for {mid}: {e}")
                continue

            buf_ids.append(mid)
            buf_docs.append(text)
            buf_metas.append(meta)
            buf_embs.append(emb)

            if len(buf_ids) >= batch_size:
                try:
                    self.collection.add(
                        ids=buf_ids, documents=buf_docs, metadatas=buf_metas, embeddings=buf_embs
                    )
                    added += len(buf_ids)
                except Exception as e:
                    logger.warning(f"⚠️ Bulk add error: {e}")
                buf_ids, buf_docs, buf_metas, buf_embs = [], [], [], []

        if buf_ids:
            try:
                self.collection.add(
                    ids=buf_ids, documents=buf_docs, metadatas=buf_metas, embeddings=buf_embs
                )
                added += len(buf_ids)
            except Exception as e:
                logger.warning(f"⚠️ Bulk add (final) error: {e}")

        return added

    # --------------------------
    # SEARCH (PATCH NO-where)
    # --------------------------
    def search_knowledge(self, query: str, n_results: int = 8) -> List[Dict[str, Any]]:
        """
        Ricerca per similarità con massima compatibilità Chroma.
        - NON passa where quando vuoto (evita: Expected where to have exactly one operator, got {}).
        - Retry senza include se necessario.
        """
        if not self.collection or self.embedding_disabled or self.embedding_model is None:
            return []

        # Cache
        cache_key = f"{query.lower().strip()}__{int(n_results)}"
        if cache_key in self.query_cache:
            return self.query_cache[cache_key]

        # Embedding query
        try:
            q_emb = self._encode(query)
        except Exception as e:
            logger.error(f"⚠️ Error generating query embedding: {e}")
            return []

        # Query Chroma
        res = None
        try:
            res = self.collection.query(
                query_embeddings=[q_emb],
                n_results=int(n_results),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            err = str(e)
            if "Expected where to have exactly one operator" in err or "where" in err:
                # Retry senza include (massima compatibilità vecchie versioni)
                try:
                    res = self.collection.query(
                        query_embeddings=[q_emb],
                        n_results=int(n_results),
                    )
                except Exception as e2:
                    logger.error(f"❌ Chroma retry failed: {e2}")
                    return []
            else:
                logger.error(f"❌ Chroma query error: {e}")
                return []

        docs = res.get("documents", [[]])
        metas = res.get("metadatas", [[]]) if "metadatas" in res else [[] for _ in docs]
        dists = res.get("distances", [[]]) if "distances" in res else [[] for _ in docs]

        formatted: List[Dict[str, Any]] = []
        if docs and len(docs[0]) > 0:
            L = len(docs[0])
            for i in range(L):
                text = docs[0][i] if i < len(docs[0]) else ""
                meta = metas[0][i] if metas and metas[0] and i < len(metas[0]) else {}
                dist = dists[0][i] if dists and dists[0] and i < len(dists[0]) else 1.0

                # Similarità “safe”
                if dist <= 1.0:
                    sim = 1.0 - float(dist)
                else:
                    sim = max(0.0, 2.0 - float(dist))

                # Boost parole chiave
                q_tokens = query.lower().split()
                kw = sum(1 for t in q_tokens if t in text.lower())
                if kw:
                    sim = min(1.0, sim + 0.1 * kw)

                formatted.append(
                    {
                        "text": text,
                        "metadata": meta or {},
                        "distance": float(dist),
                        "cosine_similarity": float(sim),
                        "relevance_score": float(sim),
                    }
                )

        formatted.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Cache bounded
        if len(self.query_cache) >= self.query_cache_size:
            try:
                self.query_cache.pop(next(iter(self.query_cache)))
            except Exception:
                self.query_cache.clear()
        self.query_cache[cache_key] = formatted
        return formatted

    # --------------------------
    # CONTEXT BUILDER
    # --------------------------
    def get_context_for_query(self, query: str, max_context_chars: int = 1200) -> (str, List[Dict[str, Any]]):
        """
        Costruisce un contesto testuale per LLM.
        Ritorna (context_str, used_items).
        """
        results = []
        try:
            results = self.search_knowledge(query, n_results=12)
        except Exception as e:
            logger.error(f"[KM] search_knowledge error: {e}")
            results = []

        if not results:
            return "", []

        # soglie leggere
        good = [r for r in results if r["relevance_score"] >= 0.25]
        if not good:
            good = results[:3]

        context_parts: List[str] = []
        used: List[Dict[str, Any]] = []
        curr = 0
        for r in good:
            chunk = r["text"].strip()
            if not chunk:
                continue
            if curr + len(chunk) + 3 <= max_context_chars:
                context_parts.append(f"- {chunk}")
                used.append(r)
                curr += len(chunk) + 3

        if not context_parts and results:
            # fallback: primi 2 piccoli
            for r in results[:2]:
                chunk = (r["text"] or "")[:max(0, max_context_chars // 2)]
                if chunk:
                    context_parts.append(f"- {chunk}")
                    used.append(r)

        context = "Informazioni verificate dal database:\n" + "\n".join(context_parts) if context_parts else ""
        return context, used

    # --------------------------
    # LOAD JSONL
    # --------------------------
    def load_from_jsonl(self, jsonl_path: str) -> int:
        if not os.path.exists(jsonl_path):
            logger.warning(f"❌ JSONL non trovato: {jsonl_path}")
            return 0

        to_add: List[Dict[str, Any]] = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception as e:
                    logger.warning(f"⚠️ JSONL parse error: {e}")
                    continue

                text = row.get("text", "")
                if not text:
                    continue
                meta = _safe_metadata(row.get("metadata", {}))
                did = row.get("id") or str(uuid.uuid4())

                to_add.append({"id": did, "text": text, "metadata": meta})

        added = self.add_bulk(to_add, batch_size=64)
        logger.info(f"✅ Loaded {added} items from {os.path.basename(jsonl_path)}")
        return added

    # --------------------------
    # MAINTENANCE
    # --------------------------
    def reset_database(self) -> bool:
        try:
            assert self.client is not None
            self.client.reset()
            self.collection = self.client.create_collection(
                name=self.collection_name, metadata={"description": "Fantacalcio knowledge base for RAG"}
            )
            self.query_cache.clear()
            return True
        except Exception as e:
            logger.error(f"❌ reset_database error: {e}")
            return False

    def rebuild_database_from_jsonl(self, jsonl_files: List[str]) -> int:
        if not self.reset_database():
            return 0
        total = 0
        for fp in jsonl_files:
            try:
                total += self.load_from_jsonl(fp)
            except Exception as e:
                logger.error(f"❌ rebuild error for {fp}: {e}")
        return total

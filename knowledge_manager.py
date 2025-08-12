# knowledge_manager.py
# -*- coding: utf-8 -*-

import os
import logging
from typing import Any, Dict, List, Optional

import chromadb
from sentence_transformers import SentenceTransformer

LOG = logging.getLogger("knowledge_manager")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def _abs_chroma_path() -> str:
    """
    Risolve CHROMA_PATH in un percorso assoluto stabile rispetto a questo file.
    Evita che './chroma_db' punti a cartelle diverse se la cwd cambia.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.getenv("CHROMA_PATH", "./chroma_db")  # tuo valore storico
    path = env_path
    if not os.path.isabs(env_path):
        path = os.path.abspath(os.path.join(base_dir, env_path))
    return path


def _make_chroma_client():
    """
    Priorità:
    - CHROMA_HOST/PORT => HttpClient
    - altrimenti PersistentClient(path=CHROMA_PATH assoluto)
    - fallback: Client() in-process (con log di warning)
    """
    host = os.getenv("CHROMA_HOST")
    port = int(os.getenv("CHROMA_PORT", "8000"))
    path = _abs_chroma_path()

    if host:
        try:
            LOG.info("[KM] Using Chroma HttpClient %s:%d (CHROMA_PATH=%s non usato)", host, port, path)
            return chromadb.HttpClient(host=host, port=port)
        except Exception as e:
            LOG.warning("[KM] HttpClient error: %s (fallback to persistent)", e)

    try:
        os.makedirs(path, exist_ok=True)
        LOG.info("[KM] Using Chroma PersistentClient at %s", path)
        return chromadb.PersistentClient(path=path)
    except Exception as e:
        LOG.warning("[KM] PersistentClient error: %s (fallback to in-process). PATH=%s", e, path)

    LOG.warning("[KM] Using Chroma in-process Client() — dati NON persistenti!")
    return chromadb.Client()


_ALLOWED_INCLUDES = {"documents", "metadatas", "embeddings", "distances", "uris", "data"}

def _sanitize_include(include: Optional[List[str]]) -> List[str]:
    if not include:
        return ["metadatas"]
    out = [k for k in include if k in _ALLOWED_INCLUDES]
    return out or ["metadatas"]


def _normalize_where(where: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Chroma >= 0.5 richiede un unico operatore top-level.
    - None -> None
    - già contiene $and/$or/$not -> ok
    - dict con >1 chiave -> wrap in {"$and": [{k:v}, ...]}
    """
    if not where:
        return None
    if any(op in where for op in ("$and", "$or", "$not")):
        return where
    if len(where.keys()) <= 1:
        return where
    return {"$and": [{k: v} for k, v in where.items()]}


class KnowledgeManager:
    """
    Wrapper stabile per Chroma + SentenceTransformer.
    """

    def __init__(self,
                 collection_name: Optional[str] = None,
                 embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.collection_name = collection_name or os.getenv("CHROMA_COLLECTION_NAME", "fantacalcio_knowledge")
        self.client = _make_chroma_client()

        # log diagnostici
        try:
            import chromadb as _c
            LOG.info("[KM] chromadb version: %s", getattr(_c, "__version__", "unknown"))
        except Exception:
            pass
        LOG.info("[KM] Collection name: %s", self.collection_name)

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        LOG.info("🔄 Initializing SentenceTransformer (attempt 1/10)...")
        self.model = SentenceTransformer(embedding_model_name)
        LOG.info("✅ SentenceTransformer initialized successfully on attempt 1")

        # Conteggio best-effort
        try:
            raw = self.collection.get(include=["metadatas"])
            cnt = len(raw.get("metadatas", []) or [])
            LOG.info("[KM] Collection caricata: '%s', count=%d", self.collection_name, cnt)
        except Exception as e:
            LOG.warning("[KM] Impossibile contare i documenti: %s", e)

    def get_by_filter(self,
                      where: Optional[Dict[str, Any]] = None,
                      limit: int = 100,
                      include: Optional[List[str]] = None) -> Dict[str, Any]:
        include = _sanitize_include(include)
        where = _normalize_where(where)
        try:
            return self.collection.get(where=where, limit=limit, include=include)
        except Exception as e:
            LOG.error("[KM] get_by_filter error: %s", e)
            return {"metadatas": [], "documents": []}

    def query_by_text(self,
                      text: str,
                      where: Optional[Dict[str, Any]] = None,
                      n_results: int = 10,
                      include: Optional[List[str]] = None) -> Dict[str, Any]:
        include = _sanitize_include(include)
        where = _normalize_where(where)
        if not text:
            return {"metadatas": [], "documents": []}
        try:
            emb = self.model.encode([text]).tolist()
            res = self.collection.query(
                query_embeddings=emb,
                where=where,
                n_results=n_results,
                include=include
            )
            # Flatten lists-of-lists
            out: Dict[str, Any] = {}
            for k, v in res.items():
                if isinstance(v, list) and v and isinstance(v[0], list):
                    out[k] = v[0]
                else:
                    out[k] = v
            return out
        except Exception as e:
            LOG.error("[KM] query_by_text error: %s", e)
            return {"metadatas": [], "documents": []}

    def search_knowledge(self,
                         text: Optional[str] = None,
                         where: Optional[Dict[str, Any]] = None,
                         n_results: int = 10,
                         include: Optional[List[str]] = None,
                         **kwargs) -> Dict[str, Any]:
        if text:
            return self.query_by_text(text=text, where=where, n_results=n_results, include=include)
        return self.get_by_filter(where=where, limit=n_results, include=include)

    def upsert(self,
               ids: List[str],
               documents: Optional[List[str]] = None,
               metadatas: Optional[List[Dict[str, Any]]] = None,
               embeddings: Optional[List[List[float]]] = None) -> None:
        try:
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        except Exception as e:
            LOG.error("[KM] upsert error: %s", e)

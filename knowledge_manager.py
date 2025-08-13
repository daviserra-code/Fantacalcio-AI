# knowledge_manager.py
# -*- coding: utf-8 -*-
import os
import logging
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer

LOG = logging.getLogger("knowledge_manager")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

class KnowledgeManager:
    """
    Wrapper per Chroma con:
    - PersistentClient (CHROMA_PATH)
    - normalizzazione filtri (where) in sintassi valida ($and/$or/$eq/$in)
    - metodi: get_by_filter, search_knowledge
    """
    def __init__(self, collection_name: str = "fantacalcio_knowledge") -> None:
        chroma_path = os.getenv("CHROMA_PATH", "./chroma_db")
        self.client = chromadb.PersistentClient(path=chroma_path, settings=Settings(allow_reset=False))
        LOG.info("[KM] Using Chroma PersistentClient at %s", os.path.abspath(chroma_path))

        self.collection = self.client.get_or_create_collection(name=collection_name)
        LOG.info("[KM] Collection caricata: '%s', count=%d", collection_name, self.collection.count())

        # Embeddings
        LOG.info("🔄 Initializing SentenceTransformer (attempt 1/10)...")
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        LOG.info("✅ SentenceTransformer initialized successfully on attempt 1")

    # ---------- filter normalization ----------
    def _normalize_where(self, where: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if where is None:
            return None
        # se già contiene un operatore top-level supportato, passo through
        if any(k in where for k in ("$and", "$or", "$nor", "$not")):
            return where

        # altrimenti converto chiavi semplici in $and di $eq
        parts = []
        for k, v in where.items():
            if isinstance(v, dict):
                parts.append({k: v})
            else:
                parts.append({k: {"$eq": v}})
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return {"$and": parts}

    # ---------- public ----------
    def get_by_filter(self, where: Optional[Dict[str, Any]], limit: int = 100, include: Optional[List[str]] = None) -> Dict[str, Any]:
        include = include or ["documents", "metadatas"]
        include = [x for x in include if x in {"documents", "embeddings", "metadatas", "distances", "uris", "data"}]
        where_n = self._normalize_where(where)
        raw = self.collection.get(where=where_n, limit=limit, include=include)
        # garantisco chiavi presenti
        out = {k: raw.get(k) for k in include}
        return out

    def search_knowledge(self,
                         text: Optional[str] = None,
                         where: Optional[Dict[str, Any]] = None,
                         n_results: int = 20,
                         include: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Se text è None → usa get_by_filter; altrimenti (se disponibile) query per embeddings.
        """
        include = include or ["documents", "metadatas", "distances"]
        include = [x for x in include if x in {"documents", "embeddings", "metadatas", "distances", "uris", "data"}]

        where_n = self._normalize_where(where)
        if not text:
            return self.get_by_filter(where=where_n, limit=n_results, include=include)

        # query vettoriale
        emb = self.model.encode([text]).tolist()
        # Chroma 0.5+ usa 'query' in collection
        res = self.collection.query(
            query_embeddings=emb,
            n_results=n_results,
            where=where_n,
            include=include
        )
        out = {k: res.get(k) for k in ("documents", "metadatas", "distances", "ids") if k in include or k == "ids"}
        return out

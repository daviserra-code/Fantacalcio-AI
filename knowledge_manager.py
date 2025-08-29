# knowledge_manager.py
# -*- coding: utf-8 -*-
import os
import logging
from typing import Any, Dict, List, Optional
import time
import shutil

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
    def __init__(self) -> None:
        LOG.info("[KM] Initializing KnowledgeManager...")
        db_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
        collection_name = os.getenv("CHROMA_COLLECTION_NAME", "fantacalcio_knowledge")

        try:
            self.client = chromadb.PersistentClient(path=db_path)
            LOG.info("[KM] Using Chroma PersistentClient at %s", db_path)
        except Exception as e:
            LOG.error("[KM] ChromaDB corruption detected: %s", e)
            # Try to backup and recreate
            backup_path = f"{db_path}_backup_{int(time.time())}"
            try:
                shutil.move(db_path, backup_path)
                LOG.info("[KM] Backed up corrupted DB to %s", backup_path)
            except Exception:
                pass

            # Create fresh client
            self.client = chromadb.PersistentClient(path=db_path)
            LOG.info("[KM] Created fresh ChromaDB at %s", db_path)

        # Try to get existing collection, create if doesn't exist or is corrupted
        try:
            self.collection = self.client.get_collection(name=collection_name)
            # Test if collection is accessible
            count = self.collection.count()
            LOG.info("[KM] Collection caricata: '%s', count=%d", collection_name, count)
        except Exception as e:
            LOG.info("[KM] Collection non trovata o corrotta (%s), creazione: '%s'", e, collection_name)
            # Try to delete any existing corrupted collection
            try:
                self.client.delete_collection(name=collection_name)
                LOG.info("[KM] Deleted corrupted collection")
            except Exception:
                pass  # Ignore errors when deleting

            # Create fresh collection
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "Fantacalcio knowledge base for RAG"}
            )
            LOG.info("[KM] Fresh collection created: '%s'", collection_name)

        self.collection_name = collection_name


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

    def add_knowledge(self, text: str, metadata: Optional[Dict[str, Any]] = None, 
                     id: Optional[str] = None) -> None:
        """Add a single document to the knowledge base"""
        import uuid
        if id is None:
            id = str(uuid.uuid4())
        
        try:
            self.collection.add(
                documents=[text],
                metadatas=[metadata or {}],
                ids=[id]
            )
            LOG.debug("[KM] Added document with id: %s", id)
        except Exception as e:
            LOG.error("[KM] Error adding document: %s", e)
            raise
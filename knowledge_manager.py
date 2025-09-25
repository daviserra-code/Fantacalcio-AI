# knowledge_manager.py
# -*- coding: utf-8 -*-
import os
import logging
from typing import Any, Dict, List, Optional
import time
import shutil
from datetime import datetime

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

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

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Ensure directory exists and has proper permissions
                os.makedirs(db_path, exist_ok=True)
                
                # Try to create client with settings for better stability
                settings = chromadb.config.Settings(
                    persist_directory=db_path,
                    anonymized_telemetry=False,
                    allow_reset=True
                )
                self.client = chromadb.PersistentClient(path=db_path, settings=settings)
                
                # Test the connection
                self.client.heartbeat()
                LOG.info("[KM] Using Chroma PersistentClient at %s", db_path)
                break
                
            except Exception as e:
                LOG.error("[KM] ChromaDB error (attempt %d/%d): %s", attempt + 1, max_retries, e)
                
                if attempt < max_retries - 1:
                    # Try to recover on non-final attempts
                    backup_path = f"{db_path}_backup_{int(time.time())}"
                    try:
                        if os.path.exists(db_path):
                            shutil.move(db_path, backup_path)
                            LOG.info("[KM] Backed up corrupted DB to %s", backup_path)
                    except Exception as backup_error:
                        LOG.warning("[KM] Backup failed: %s", backup_error)
                    
                    # Clean up and retry
                    time.sleep(1)
                    continue
                else:
                    # Final attempt failed, create minimal client
                    LOG.error("[KM] All ChromaDB attempts failed, creating in-memory client")
                    self.client = chromadb.Client()
                    break

        # Try to get existing collection, create if doesn't exist or is corrupted
        collection_attempts = 0
        max_collection_attempts = 2
        
        while collection_attempts < max_collection_attempts:
            try:
                self.collection = self.client.get_collection(name=collection_name)
                # Test if collection is accessible with multiple operations
                count = self.collection.count()
                
                # Additional stability check - try a simple query
                try:
                    self.collection.peek(limit=1)
                    LOG.info("[KM] Collection verified stable: '%s', count=%d", collection_name, count)
                    break
                except Exception as query_error:
                    LOG.warning("[KM] Collection query test failed: %s", query_error)
                    raise query_error
                    
            except Exception as e:
                collection_attempts += 1
                LOG.info("[KM] Collection issue (attempt %d/%d): %s", collection_attempts, max_collection_attempts, e)
                
                # Try to delete any existing corrupted collection
                try:
                    self.client.delete_collection(name=collection_name)
                    LOG.info("[KM] Deleted problematic collection")
                except Exception:
                    pass  # Ignore errors when deleting

                # Create fresh collection with enhanced metadata
                try:
                    self.collection = self.client.create_collection(
                        name=collection_name,
                        metadata={
                            "description": "Fantacalcio knowledge base for RAG",
                            "created_at": str(datetime.now()),
                            "version": "2.0"
                        }
                    )
                    LOG.info("[KM] Fresh collection created: '%s'", collection_name)
                    break
                except Exception as create_error:
                    if collection_attempts >= max_collection_attempts:
                        LOG.error("[KM] Failed to create collection after %d attempts: %s", max_collection_attempts, create_error)
                        raise create_error

        self.collection_name = collection_name

        # Lazy load SentenceTransformer model for faster startup
        self.model = None
        self._model_loading = False
        LOG.info("🚀 KnowledgeManager initialized with lazy model loading")

    def _ensure_model_loaded(self):
        """Lazy load SentenceTransformer model when needed"""
        if self.model is not None:
            return

        if self._model_loading:
            # Another thread is loading, wait briefly
            import time
            time.sleep(0.1)
            return

        self._model_loading = True
        try:
            LOG.info("🔄 Loading SentenceTransformer model on-demand...")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            LOG.info("✅ SentenceTransformer model loaded successfully")
        except Exception as e:
            LOG.error(f"❌ Failed to load SentenceTransformer model: {e}")
            self.model = None
        finally:
            self._model_loading = False

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
        self._ensure_model_loaded()
        if self.model is None:
            LOG.warning("SentenceTransformer model not available, falling back to text search")
            return self.get_by_filter(where=where_n, limit=n_results, include=include)
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

        # Filter out None values from metadata - ChromaDB only accepts str, int, float, bool
        clean_metadata = {}
        if metadata:
            for k, v in metadata.items():
                if v is not None:
                    # Convert to string if not a basic type
                    if isinstance(v, (str, int, float, bool)):
                        clean_metadata[k] = v
                    else:
                        clean_metadata[k] = str(v)

        try:
            self.collection.add(
                documents=[text],
                metadatas=[clean_metadata],
                ids=[id]
            )
            LOG.debug("[KM] Added document with id: %s", id)
        except Exception as e:
            LOG.error("[KM] Error adding document: %s", e)
            raise
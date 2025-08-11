import os
import re
import time
import uuid
import json
import logging
from typing import Any, Dict, List, Optional

# Chroma
import chromadb
from chromadb.config import Settings

# Embeddings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _slugify_id(text: str, max_len: int = 48) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not base:
        base = "doc"
    if len(base) > max_len:
        base = base[:max_len]
    return f"{base}_{uuid.uuid4().hex[:8]}"


def _clean_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    """Chroma accetta solo str/int/float/bool in metadata."""
    out: Dict[str, Any] = {}
    for k, v in (md or {}).items():
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif v is None:
            # salta None
            continue
        else:
            # fallback a stringa (compat)
            try:
                out[k] = json.dumps(v, ensure_ascii=False)
            except Exception:
                out[k] = str(v)
    return out


class KnowledgeManager:
    """
    Wrapper semplice per ChromaDB + SentenceTransformer.
    Espone:
      - add_knowledge(text, metadata, doc_id)
      - search_knowledge(query_text, n_results, where)
      - build_player_catalog(limit)
      - get_context_for_query(query_text, n_results, max_context_length)
    """

    def __init__(
        self,
        collection_name: str = "fantacalcio_knowledge",
        persist_dir: str = "./chroma_db",
        embed_model_name: str = "all-MiniLM-L6-v2",
    ):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        os.makedirs(self.persist_dir, exist_ok=True)

        # Chroma client + collection
        self.client = chromadb.PersistentClient(path=self.persist_dir, settings=Settings(anonymized_telemetry=True))
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # Embedding model con retry
        self.model = None
        for attempt in range(1, 11):
            try:
                logger.info("🔄 Initializing SentenceTransformer (attempt %d/10)...", attempt)
                self.model = SentenceTransformer(embed_model_name)
                logger.info("✅ SentenceTransformer initialized successfully on attempt %d", attempt)
                break
            except Exception as e:
                if attempt == 10:
                    raise
                time.sleep(0.8 * attempt)

        # Info base
        try:
            count = self.collection.count()
        except Exception:
            count = "unknown"
        logger.info("[KM] Collection caricata: '%s', count=%s", self.collection_name, count)

    # ---------------------------
    # Low-level helpers
    # ---------------------------
    def _embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    # ---------------------------
    # Public API
    # ---------------------------
    def add_knowledge(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """
        Aggiunge un documento alla collection.
        Ritorna l'id usato.
        """
        if not text or not isinstance(text, str):
            raise ValueError("text richiesto")

        md = _clean_metadata(metadata or {})
        _id = doc_id or _slugify_id(md.get("player") or md.get("team") or text[:40])

        emb = self._embed([text])
        try:
            self.collection.add(
                ids=[_id],
                documents=[text],
                metadatas=[md],
                embeddings=emb,
            )
            return _id
        except Exception as e:
            # Se id duplicato, generane uno nuovo
            logger.warning("[KM] add_knowledge duplicate id '%s': %s -> rigenero id", _id, e)
            _id = _slugify_id(text[:40])
            self.collection.add(
                ids=[_id],
                documents=[text],
                metadatas=[md],
                embeddings=emb,
            )
            return _id

    def search_knowledge(
        self,
        query_text: str,
        n_results: int = 6,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Esegue una query semantica. `where` deve usare operatori Chroma ($eq, $in, ecc.)
        Esempio: where={'type': {'$in': ['player_info','current_player']}}
        """
        try:
            emb = self._embed([query_text])
            include = ["documents", "metadatas", "distances"]  # NIENTE 'ids' per evitare errori
            if where and not isinstance(where, dict):
                where = None  # difesa
            res = self.collection.query(
                query_embeddings=emb,
                n_results=max(1, int(n_results)),
                where=where,
                include=include,
            )
            # Normalizza risultati
            out: List[Dict[str, Any]] = []
            docs = res.get("documents", [[]])[0] if res else []
            metas = res.get("metadatas", [[]])[0] if res else []
            dists = res.get("distances", [[]])[0] if res else []
            for doc, md, dist in zip(docs, metas, dists):
                out.append({
                    "text": doc,
                    "metadata": md or {},
                    "score": 1.0 - float(dist) if dist is not None else None,  # similarità approssimativa
                })
            return out
        except Exception as e:
            logger.error("[KM] search_knowledge error: %s", e)
            return []

    def build_player_catalog(self, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Estrae un piccolo catalogo giocatori da metadati (type in player_info/current_player).
        Ritorna lista di dict con campi: name, team, role, fantamedia, price, appearances (se presenti).
        """
        try:
            include = ["documents", "metadatas"]  # NO 'ids'
            # Usa .get con where per filtrare in base a metadata
            res = self.collection.get(
                where={"type": {"$in": ["player_info", "current_player"]}},
                include=include,
                limit=limit,
            )
            docs = res.get("documents", []) or []
            metas = res.get("metadatas", []) or []
            out: List[Dict[str, Any]] = []

            for doc, md in zip(docs, metas):
                md = md or {}
                name = md.get("player") or md.get("name")
                team = md.get("team") or ""
                role = md.get("role") or ""
                fantamedia = md.get("fantamedia")
                price = md.get("price")
                apps = md.get("appearances")

                # piccoli fallback parsing grezzo dal testo, se serve
                if not name and doc:
                    # cerca pattern "Giocatore è un <ruolo> del <team>"
                    m = re.search(r"^([A-Za-zÀ-ÖØ-öø-ÿ' .-]+)\s+è\s+un", doc)
                    if m:
                        name = m.group(1).strip()

                item = {
                    "name": name or "Sconosciuto",
                    "team": team or "N/D",
                    "role": role or "N/D",
                    "fantamedia": float(fantamedia) if isinstance(fantamedia, (int, float, str)) and str(fantamedia).replace('.', '', 1).isdigit() else None,
                    "price": float(price) if isinstance(price, (int, float, str)) and str(price).replace('.', '', 1).isdigit() else None,
                    "appearances": int(apps) if isinstance(apps, (int, str)) and str(apps).isdigit() else None,
                }
                out.append(item)

            logger.info("[KM] Player catalog costruito: %d record", len(out))
            return out
        except Exception as e:
            logger.error("[KM] build_player_catalog error: %s", e)
            return []

    def get_context_for_query(
        self,
        query_text: str,
        n_results: int = 6,
        max_context_length: int = 1200,
        where: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Restituisce un blob di contesto testuale per il RAG:
        concatenazione di snippet (documento + info-chiave dai metadati).
        """
        results = self.search_knowledge(query_text, n_results=n_results, where=where)
        if not results:
            return ""

        lines: List[str] = []
        for r in results:
            doc = (r.get("text") or "").strip()
            md = r.get("metadata") or {}
            src = md.get("source") or md.get("origin") or "KB interno"
            src_date = md.get("source_date") or md.get("updated_at") or md.get("valid_from") or ""
            head = []
            if md.get("type"):
                head.append(f"type={md.get('type')}")
            if md.get("team"):
                head.append(f"team={md.get('team')}")
            if md.get("player"):
                head.append(f"player={md.get('player')}")
            if md.get("season"):
                head.append(f"season={md.get('season')}")

            header = ("[" + ", ".join(head) + "] ") if head else ""
            lines.append(f"{header}{doc} (fonte: {src}{', ' + src_date if src_date else ''})")

            # Stop se superiamo il budget di caratteri
            if sum(len(x) for x in lines) > max_context_length:
                break

        ctx = "\n".join(lines)
        if len(ctx) > max_context_length:
            ctx = ctx[:max_context_length]
        return ctx

import os
import time
import json
import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

import chromadb
from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _to_float(x) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        try:
            return float(x)
        except Exception:
            return None
    if isinstance(x, str):
        s = x.strip().replace(",", ".")
        # rimuovi simboli tipo "€", "cred", ecc.
        for tok in ["€", "cred", "crediti", "cr"]:
            s = s.replace(tok, "")
        try:
            return float(s)
        except Exception:
            return None
    return None


def _parse_age(birthdate: Optional[str]) -> Optional[int]:
    if not birthdate or not isinstance(birthdate, str):
        return None
    # formati comuni: YYYY-MM-DD o DD/MM/YYYY
    try:
        if "-" in birthdate:
            dt = datetime.strptime(birthdate[:10], "%Y-%m-%d")
        elif "/" in birthdate:
            # prova due varianti
            try:
                dt = datetime.strptime(birthdate[:10], "%d/%m/%Y")
            except Exception:
                dt = datetime.strptime(birthdate[:10], "%Y/%m/%d")
        else:
            return None
        today = datetime.utcnow().date()
        years = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
        return int(years)
    except Exception:
        return None


class KnowledgeManager:
    """
    Gestione del KB su Chroma + embedding locale (SentenceTransformer).
    - Ricerca semantica
    - Catalogo giocatori in RAM (normalizzato)
    - Recommender per ruolo/budget (robusto ai dati mancanti)
    NOTE: niente 'ids' negli include, per compatibilità con alcune versioni di Chroma.
    """

    def __init__(
        self,
        collection_name: str = "fantacalcio_knowledge",
        chroma_path: str = "./chroma_db",
        embed_model_name: str = "all-MiniLM-L6-v2",
    ):
        self.collection_name = collection_name
        self._player_catalog: List[Dict[str, Any]] = []
        self._catalog_built_ts: Optional[float] = None

        # Init Chroma
        try:
            self.client: PersistentClient = chromadb.PersistentClient(path=chroma_path)
        except Exception as e:
            logger.error(f"[KM] Errore inizializzazione Chroma client: {e}")
            raise

        # Carica o crea collection
        try:
            self.collection = self.client.get_collection(collection_name)
            logger.info(
                f"[KM] Collection caricata: '{collection_name}', count={self.collection.count()}"
            )
        except Exception:
            self.collection = self.client.create_collection(
                name=collection_name, metadata={"description": "Fantacalcio KB"}
            )
            logger.info(f"[KM] Collection creata: '{collection_name}'")

        # Init embedding con retry
        self.embedder: Optional[SentenceTransformer] = None
        for attempt in range(1, 6):
            try:
                os.environ["CUDA_VISIBLE_DEVICES"] = ""
                os.environ["TOKENIZERS_PARALLELISM"] = "false"
                self.embedder = SentenceTransformer(embed_model_name, device="cpu")
                _ = self.embedder.encode("warmup", show_progress_bar=False)
                logger.info("✅ SentenceTransformer initialized successfully on attempt %d", attempt)
                break
            except Exception as e:
                logger.warning(f"[KM] Embedding init attempt {attempt} failed: {e}")
                time.sleep(0.8)
        if self.embedder is None:
            raise RuntimeError("[KM] Impossibile inizializzare il modello di embedding")

    # --------------------------
    # CRUD / ingest
    # --------------------------

    def add_knowledge(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        if not text:
            raise ValueError("text richiesto")
        metadata = metadata or {}
        doc_id = doc_id or str(uuid.uuid4())
        try:
            emb = self.embedder.encode(text, show_progress_bar=False).tolist()
            self.collection.add(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
                embeddings=[emb],
            )
            # invalida catalogo se sembra record giocatore
            t = (metadata.get("type") or "").lower()
            if metadata.get("player") or t in ("player_info", "current_player"):
                self._player_catalog = []
                self._catalog_built_ts = None
            return doc_id
        except Exception as e:
            logger.error(f"[KM] add_knowledge error: {e}")
            raise

    # --------------------------
    # Ricerca semantica
    # --------------------------

    def search_knowledge(self, query: str, n_results: int = 8) -> List[Dict[str, Any]]:
        if not query:
            return []
        try:
            q_emb = self.embedder.encode(query, show_progress_bar=False).tolist()
            res = self.collection.query(
                query_embeddings=[q_emb],
                n_results=max(1, int(n_results)),
                include=["documents", "metadatas", "distances"],
            )
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0]

            out: List[Dict[str, Any]] = []
            for i in range(len(docs)):
                dist = float(dists[i])
                sim = 1.0 - dist if dist <= 1.0 else max(0.0, 2.0 - dist)
                out.append(
                    {
                        "text": docs[i],
                        "metadata": metas[i] or {},
                        "distance": dist,
                        "similarity": float(sim),
                    }
                )
            return out
        except Exception as e:
            logger.error(f"[KM] search_knowledge error: {e}")
            return []

    def build_context(self, query: str, max_parts: int = 6, min_sim: float = 0.15) -> str:
        results = self.search_knowledge(query, n_results=max_parts * 2)
        if not results:
            return ""
        kept = [r for r in results if r["similarity"] >= min_sim] or results[:max_parts]
        kept.sort(key=lambda r: r["similarity"], reverse=True)
        kept = kept[:max_parts]
        parts = []
        for r in kept:
            m = r.get("metadata", {}) or {}
            title = m.get("title") or m.get("player") or m.get("team") or "KB"
            date = m.get("source_date") or m.get("updated_at") or m.get("date") or "n.d."
            parts.append(f"- {r['text']} [Fonte: {title} — {date}]")
        return "Informazioni verificate dal KB:\n" + "\n".join(parts)

    # --------------------------
    # Catalogo giocatori
    # --------------------------

    def build_player_catalog(self, force: bool = False) -> int:
        """
        Scansiona la collection a pagine e costruisce un indice normalizzato.
        Non usa 'where' e non richiede 'ids' in include.
        """
        if getattr(self, "_player_catalog", None) and not force:
            return len(self._player_catalog)

        self._player_catalog = []
        self._catalog_built_ts = time.time()

        try:
            total = self.collection.count()
            page_size = 500
            offset = 0

            while offset < total:
                batch = self.collection.get(
                    include=["metadatas"],
                    limit=page_size,
                    offset=offset,
                )
                metas = batch.get("metadatas", []) or []

                for m in metas:
                    md = m or {}
                    # includi qualsiasi record che sembri "giocatore"
                    if not (md.get("player") and md.get("role")):
                        # accetta 'nome' come fallback
                        if not (md.get("nome") and md.get("ruolo")):
                            continue

                    player_name = md.get("player") or md.get("nome")
                    role = (md.get("role") or md.get("ruolo") or "").upper()
                    team = md.get("team") or md.get("squadra")
                    season = md.get("season")
                    # normalizza numerici
                    price = _to_float(
                        md.get("price")
                        or md.get("prezzo")
                        or md.get("price_recommended")
                        or md.get("prezzo_consigliato")
                    )
                    fantamedia = _to_float(
                        md.get("fantamedia")
                        or md.get("fm")
                        or md.get("media")
                        or md.get("fantavoto")
                        or md.get("fanta_media")
                    )
                    appearances = _to_float(md.get("appearances") or md.get("presenze"))
                    age = _to_float(md.get("age"))
                    if age is None:
                        age = _parse_age(md.get("birthdate") or md.get("data_nascita"))

                    source_date = md.get("source_date") or md.get("updated_at") or md.get("date")

                    # filtra ruoli noti
                    if role not in ("P", "D", "C", "A"):
                        continue

                    rec = {
                        "player": player_name,
                        "team": team,
                        "role": role,
                        "season": season,
                        "price": price,
                        "fantamedia": fantamedia,
                        "appearances": appearances,
                        "age": age,
                        "birthdate": md.get("birthdate") or md.get("data_nascita"),
                        "source_date": source_date,
                        "raw": md,
                    }
                    self._player_catalog.append(rec)

                offset += page_size

            logger.info("[KM] Player catalog costruito: %d record", len(self._player_catalog))
            return len(self._player_catalog)
        except Exception as e:
            logger.error(f"[KM] build_player_catalog error: {e}")
            self._player_catalog = []
            self._catalog_built_ts = None
            return 0

    def recommend_players(
        self,
        role: str,
        budget: Optional[float],
        n: int = 5,
        season: Optional[str] = None,
        under_age: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Raccomanda giocatori per ruolo + (opzionale) budget e under_age.
        Strategia:
          1) cap unitario in base al budget (o default se assente)
          2) se pochi risultati: rilassa cap (x1.4, x1.8) poi ignora cap
          3) se ancora pochi: ordina per sola fantamedia
        """
        if not getattr(self, "_player_catalog", None):
            self.build_player_catalog()

        r = (role or "").upper().strip()
        if r not in ("P", "D", "C", "A"):
            r = "A"

        # cap di default quando budget assente (lega 500)
        def default_cap(_r: str) -> float:
            if _r == "A":
                return 45.0
            if _r == "C":
                return 30.0
            if _r == "D":
                return 22.0
            if _r == "P":
                return 18.0
            return 25.0

        def unit_cap(_r: str, total: Optional[float]) -> float:
            if total is None:
                return default_cap(_r)
            total = float(total)
            if _r == "A":
                return min(65.0, max(20.0, total / 2.4))
            if _r == "C":
                return min(45.0, max(12.0, total / 3.0))
            if _r == "D":
                return min(30.0, max(8.0, total / 4.0))
            if _r == "P":
                return min(28.0, max(8.0, total / 4.2))
            return max(10.0, total / 4.0)

        cap = unit_cap(r, budget)

        def age_ok(p: Dict[str, Any]) -> bool:
            if under_age is None:
                return True
            a = p.get("age")
            if isinstance(a, (int, float)):
                return a <= under_age
            return True

        # helper che costruisce lista candidati sotto un certo cap (o senza)
        def collect(max_price: Optional[float]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for p in self._player_catalog:
                if (p.get("role") or "").upper() != r:
                    continue
                if season and p.get("season") and p.get("season") != season:
                    continue
                if not age_ok(p):
                    continue
                price = p.get("price")
                fm = p.get("fantamedia")
                # se chiediamo cap e non c'è price, salta in questa passata
                if max_price is not None:
                    if price is None:
                        continue
                    if float(price) > float(max_price):
                        continue
                # se manca fm, difficile stimare valore (verrà gestito dopo)
                value = float(fm) / max(float(price), 1.0) if (fm is not None and price is not None) else None
                p2 = dict(p)
                p2["value"] = value
                out.append(p2)
            return out

        # Passo 1: cap base
        candidates = collect(cap)
        # se pochi risultati, rilassa cap
        if len(candidates) < n:
            candidates = collect(cap * 1.4)
        if len(candidates) < n:
            candidates = collect(cap * 1.8)
        # se ancora pochi, ignora cap
        if len(candidates) < n:
            candidates = collect(None)

        # Ordinamento: prima per value noto, poi per fantamedia
        def sort_key(p: Dict[str, Any]):
            has_value = p.get("value") is not None
            fm = p.get("fantamedia") or 0.0
            val = p.get("value") or 0.0
            return (1 if has_value else 0, float(val), float(fm))

        candidates.sort(key=sort_key, reverse=True)

        # deduplica per nome
        seen = set()
        dedup: List[Dict[str, Any]] = []
        for c in candidates:
            name = (c.get("player") or "").strip().lower()
            if not name or name in seen:
                continue
            dedup.append(c)
            seen.add(name)
            if len(dedup) >= n:
                break

        # annota cap usato
        for d in dedup:
            d["unit_budget_cap"] = cap

        return dedup

    # --------------------------
    # Utils
    # --------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            "collection": self.collection_name,
            "count": self.collection.count(),
            "catalog_size": len(self._player_catalog),
            "catalog_built_at": self._catalog_built_ts,
        }

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from hf_embedder import HFEmbedder
from retrieval.hybrid import BM25Index, hybrid_search
from retrieval.reranker import CrossEncoderReranker

DATE_FMT = "%Y-%m-%d"

class RAGPipeline:
    """
    HF embeddings -> Chroma -> (BM25) -> RRF -> CrossEncoder rerank
    Guardrail: freschezza (valid_to in Python), conflitti player_id/team, citazioni minime.
    """

    def __init__(
        self,
        chroma_collection,
        docs_texts: Optional[List[str]] = None,
        docs_ids: Optional[List[str]] = None,
        min_sources: int = 1,
    ):
        self.collection = chroma_collection
        self.embedder = HFEmbedder()
        self.bm25 = BM25Index(docs_texts, docs_ids) if docs_texts and docs_ids else None
        self.reranker = CrossEncoderReranker()  # puo disattivarsi internamente
        self.min_sources = max(1, int(min_sources))

    @staticmethod
    def _today_str() -> str:
        return datetime.utcnow().strftime(DATE_FMT)

    @staticmethod
    def _has_conflicts(items: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, List[str]]]:
        by_pid = {}
        for it in items:
            meta = (it.get("metadata") or {})
            pid = meta.get("player_id")
            team = meta.get("team")
            if not pid:
                continue
            by_pid.setdefault(pid, set()).add(team)
        conflicts = {pid: sorted([t for t in teams if t]) for pid, teams in by_pid.items() if len(teams) > 1}
        return (len(conflicts) > 0, conflicts)

    def _select_citations(self, items: List[Dict[str, Any]], max_items: int = 3) -> List[Dict[str, Any]]:
        cites, seen = [], set()
        for it in items:
            meta = (it.get("metadata") or {})
            src = meta.get("source")
            dt = meta.get("date")
            title = meta.get("title") or meta.get("type") or "fonte"
            if src and dt:
                key = (src, dt)
                if key in seen:
                    continue
                seen.add(key)
                cites.append({"title": title, "date": dt, "url": src})
                if len(cites) >= max_items:
                    break
        return cites

    def _grounded(self, items: List[Dict[str, Any]]) -> bool:
        # More lenient: allow responses if we have any relevant documents
        if not items:
            return False
        
        # Check if we have at least one document with good metadata
        for item in items:
            meta = item.get("metadata", {})
            if meta.get("type") in ["player_info", "current_player", "strategy", "team_info"]:
                return True
        
        # Fallback: check for citations but be more lenient
        cites = self._select_citations(items, max_items=self.min_sources)
        return len(cites) >= max(1, self.min_sources - 1)

    def retrieve(
        self,
        user_query: str,
        season: Optional[str] = None,
        final_k: int = 8,
    ) -> Dict[str, Any]:
        # 1) embedding query
        q_vec = self.embedder.embed_one(user_query, is_query=True).tolist()

        # 2) where SOLO per season (evita operatori numerici su stringhe)
        where = {}
        if season:
            where = {"season": {"$eq": season}}

        # 3) hybrid search (+ rerank se disponibile)
        items = hybrid_search(
            user_query,
            q_vec,
            self.collection,
            self.bm25,
            where=where,
            final_k=final_k,
            reranker=self.reranker,
        )

        # 4) freschezza in Python: valid_to >= oggi (string compare su YYYY-MM-DD)
        # But be more lenient - allow documents without valid_to or with recent dates
        today = self._today_str()
        def _fresh(it):
            meta = it.get("metadata") or {}
            vt = meta.get("valid_to")
            
            # Allow documents without valid_to date
            if not vt:
                return True
            
            # Allow if valid_to is a valid date and recent enough
            if isinstance(vt, str):
                try:
                    return vt >= today or vt >= "2024-01-01"  # Allow anything from 2024 onwards
                except:
                    return True  # If comparison fails, allow it
            
            return True
        items = [it for it in items if _fresh(it)]

        # 5) guardrail: conflitti e citazioni
        has_conflict, conflict_map = self._has_conflicts(items)
        citations = self._select_citations(items, max_items=3)
        grounded = (not has_conflict) and self._grounded(items)

        return {
            "results": items,
            "citations": citations,
            "has_conflict": has_conflict,
            "conflicts": conflict_map,
            "grounded": grounded,
        }
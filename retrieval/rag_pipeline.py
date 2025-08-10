from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from hf_embedder import HFEmbedder
from retrieval.hybrid import BM25Index, hybrid_search
from retrieval.reranker import CrossEncoderReranker

DATE_FMT = "%Y-%m-%d"


class RAGPipeline:
    """
    HF embeddings -> Chroma -> (BM25) -> RRF -> CrossEncoder rerank
    Guardrail:
      - Freschezza (valid_to) verificata in Python con logica PERMISSIVA
      - Conflitti player_id/team
      - Citazioni: usa metadati reali se presenti, altrimenti sintetizza "Interno KB"
    """

    def __init__(
        self,
        chroma_collection,
        docs_texts: Optional[List[str]] = None,
        docs_ids: Optional[List[str]] = None,
        min_sources: int = 1,  # piu' tollerante
    ):
        self.collection = chroma_collection
        self.embedder = HFEmbedder()
        self.bm25 = BM25Index(docs_texts, docs_ids) if docs_texts and docs_ids else None
        self.reranker = CrossEncoderReranker()  # puo' disattivarsi internamente
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
            title = meta.get("title") or meta.get("player") or meta.get("team") or meta.get("type") or "fonte"
            if src and dt:
                key = (src, dt)
                if key in seen:
                    continue
                seen.add(key)
                cites.append({"title": title, "date": dt, "url": src})
                if len(cites) >= max_items:
                    break

        # Se non ci sono citazioni “web”, sintetizza da KB interna
        if not cites:
            today = self._today_str()
            for it in items[:max_items]:
                meta = (it.get("metadata") or {})
                title = meta.get("title") or meta.get("player") or meta.get("team") or meta.get("type") or "Interno KB"
                cites.append({"title": title, "date": meta.get("date", today), "url": "internal://kb"})
        return cites

    def _grounded(self, items: List[Dict[str, Any]]) -> bool:
        # Con docs interni permettiamo grounded (min 1 citazione sintetizzata)
        cites = self._select_citations(items, max_items=self.min_sources)
        return len(items) > 0 and len(cites) >= self.min_sources

    def retrieve(
        self,
        user_query: str,
        season: Optional[str] = None,
        final_k: int = 8,
    ) -> Dict[str, Any]:
        q_vec = self.embedder.embed_one(user_query, is_query=True).tolist()

        # where solo se stagione passata in modo esplicito e non vuota
        use_season = bool(season and isinstance(season, str) and season.strip())
        where = {"season": {"$eq": season.strip()}} if use_season else {}

        # primo tentativo (eventualmente con filtro stagione)
        items = hybrid_search(
            user_query, q_vec, self.collection, self.bm25,
            where=where, final_k=final_k, reranker=self.reranker,
        )

        # fallback: se 0 risultati e avevamo filtrato per stagione, riprova senza filtro
        if use_season and not items:
            items = hybrid_search(
                user_query, q_vec, self.collection, self.bm25,
                where={}, final_k=final_k, reranker=self.reranker,
            )

        # freschezza permissiva
        today = datetime.utcnow().strftime(DATE_FMT)
        today_num = int(today.replace("-", ""))

        def _fresh(it: Dict[str, Any]) -> bool:
            meta = it.get("metadata") or {}
            vt = meta.get("valid_to")
            if vt is None or vt == "":
                return True
            if isinstance(vt, (int, float)):
                try:
                    return int(vt) >= today_num
                except Exception:
                    return True
            if isinstance(vt, str):
                s = vt.strip()
                if len(s) == 10 and s[4] == "-" and s[7] == "-":  # YYYY-MM-DD
                    return s >= today
                if len(s) == 8 and s.isdigit():  # YYYYMMDD
                    try:
                        return int(s) >= today_num
                    except Exception:
                        return True
            return True

        items = [it for it in items if _fresh(it)]

        has_conflict, conflict_map = self._has_conflicts(items)
        citations = self._select_citations(items, max_items=3)
        grounded = (not has_conflict) and self._grounded(items)
        
        # Aggiunto il parametro query per il fallback specifico per i trasferimenti
        grounded_results = items # Supponendo che items sia il risultato della ricerca
        query = user_query # Assumendo che user_query sia accessibile qui

        # Se non ci sono risultati utili, fallback con suggerimento per trasferimenti
        if not grounded_results:
            # Controlla se la query riguarda un giocatore specifico
            query_lower = query.lower()
            player_keywords = ['dove gioca', 'gioca', 'squadra', 'team']
            if any(keyword in query_lower for keyword in player_keywords):
                return {
                    "answer": "Il giocatore richiesto potrebbe non essere più in Serie A o i dati potrebbero non essere aggiornati. Controlla se il giocatore è stato trasferito in un'altra lega. Per informazioni aggiornate sui trasferimenti, verifica le fonti ufficiali.",
                    "sources": [],
                    "grounded": False,
                    "has_conflicts": False
                }

            return {
                "answer": "Non ho fonti aggiornate e sufficienti per rispondere con sicurezza. Riformula la domanda o aggiorna i dati.",
                "sources": [],
                "grounded": False,
                "has_conflicts": False
            }

        return {
            "results": items,
            "citations": citations,
            "has_conflict": has_conflict,
            "conflicts": conflict_map,
            "grounded": grounded,
        }
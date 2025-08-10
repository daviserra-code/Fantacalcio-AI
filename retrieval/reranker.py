from typing import List, Dict, Any

class CrossEncoderReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = None  # stub: nessun rerank

    def rerank(self, query: str, items: List[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
        # no-op: restituisce i primi top_k così come arrivano
        return items[:top_k]
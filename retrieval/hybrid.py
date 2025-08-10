from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

def reciprocal_rank_fusion(rank_lists: List[List[Dict[str, Any]]], k: int = 60) -> List[Dict[str, Any]]:
    """
    Fonde piu ranking (dense/sparse) usando RRF.
    Ogni item deve avere una chiave 'id'.
    """
    scores = {}
    for rlist in rank_lists:
        for rank, item in enumerate(rlist):
            rid = item["id"]
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (rank + k)

    # ricostruisci items unici preservando i metadati piu ricchi
    by_id = {}
    for rlist in rank_lists:
        for it in rlist:
            by_id.setdefault(it["id"], it)

    fused = sorted(by_id.values(), key=lambda x: scores.get(x["id"], 0.0), reverse=True)
    return fused

class BM25Index:
    """
    Indice BM25 semplice: costruiscilo a startup con tutti i testi/ids.
    """
    def __init__(self, docs: List[str], ids: List[str]):
        self.ids = ids
        # tokenizziamo banalmente su split(); per risultati migliori usa una tokenizzazione piu furba
        self.docs_tok = [d.split() for d in docs]
        self.bm25 = BM25Okapi(self.docs_tok)

    def search(self, query: str, top_k: int = 100) -> List[Dict[str, Any]]:
        qtok = query.split()
        scores = self.bm25.get_scores(qtok)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        out = []
        for i in ranked:
            out.append({
                "id": self.ids[i],
                # ricostruiamo un testo grezzo (serve solo per il rerank o debug)
                "text": " ".join(self.docs_tok[i]),
                "bm25_score": float(scores[i])
            })
        return out

def chroma_search(collection, query_vec, where: Optional[dict] = None, top_k: int = 100) -> List[Dict[str, Any]]:
    """
    Query su Chroma usando l'embedding della query.
    Ritorna una lista di dict con id, text, metadata, dense_score.
    """
    res = collection.query(query_embeddings=[query_vec], n_results=top_k, where=where or {})
    out = []
    # chroma ritorna liste per query; assumiamo 1 query per call
    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0] if "distances" in res else [None] * len(ids)
    for i in range(len(ids)):
        out.append({
            "id": ids[i],
            "text": docs[i],
            "metadata": metas[i] if isinstance(metas, list) else {},
            "dense_score": float(dists[i]) if dists and dists[i] is not None else None
        })
    return out

def hybrid_search(
    query: str,
    query_vec,
    collection,
    bm25_index: Optional[BM25Index] = None,
    where: Optional[dict] = None,
    final_k: int = 8,
    reranker=None
) -> List[Dict[str, Any]]:
    """
    1) Dense (Chroma) + 2) Sparse (BM25, se presente) -> 3) RRF
    4) Rerank (CrossEncoder, se presente) -> top_k
    """
    dense = chroma_search(collection, query_vec, where=where, top_k=max(100, final_k))
    sparse = bm25_index.search(query, top_k=100) if bm25_index else []

    fused = reciprocal_rank_fusion([dense, sparse], k=60)

    # arricchisci gli item provenienti da sparse con i metadata se disponibili in dense
    meta_by_id = {d["id"]: d.get("metadata") for d in dense if d.get("metadata")}
    text_by_id = {d["id"]: d.get("text") for d in dense}
    items = []
    for it in fused:
        rid = it["id"]
        it["metadata"] = it.get("metadata") or meta_by_id.get(rid, {})
        it["text"] = it.get("text") or text_by_id.get(rid, it.get("text", ""))
        items.append(it)

    if reranker:
        # il tuo CrossEncoderReranker ha metodo rerank(query, items, top_k)
        items = reranker.rerank(query, items, top_k=final_k)
    else:
        items = items[:final_k]

    return items
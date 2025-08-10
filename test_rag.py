import os
import sys
from datetime import datetime

if not os.environ.get("HF_TOKEN"):
    print("Manca HF_TOKEN nei Secrets di Replit.")
    sys.exit(1)

from knowledge_manager import KnowledgeManager
from retrieval.helpers import dump_chroma_texts_ids
from retrieval.rag_pipeline import RAGPipeline

def today():
    return datetime.utcnow().strftime("%Y-%m-%d")

def ensure_seed_docs(km):
    try:
        n = km.collection.count()
    except Exception:
        n = 0

    if n and n > 0:
        print("Collection gia popolata ({} documenti).".format(n))
        return

    print("Collection vuota: carico documenti seed...")
    seed = [
        {
            "id": "tonali_team_current",
            "text": "Sandro Tonali e un centrocampista del Newcastle United (Premier League).",
            "metadata": {
                "player_id": "tonali_sandro",
                "team": "Newcastle",
                "role": "C",
                "type": "trasferimento",
                "season": "2025-26",
                "date": today(),
                "valid_from": "2023-07-03",
                "valid_to": "2099-01-01",
                "source": "https://example.com/tonali-newcastle",
                "title": "Profilo Tonali"
            }
        },
        {
            "id": "koop_asta_tip",
            "text": "Koopmeiners e un centrocampista affidabile per l'asta: titolare fisso nell'Atalanta, bonus costanti.",
            "metadata": {
                "player_id": "koopmeiners_tev",
                "team": "Atalanta",
                "role": "C",
                "type": "consiglio",
                "season": "2025-26",
                "date": today(),
                "valid_from": today(),
                "valid_to": "2099-01-01",
                "source": "https://example.com/koop-analisi",
                "title": "Analisi Koopmeiners"
            }
        },
    ]
    for d in seed:
        km.add_knowledge(d["text"], d["metadata"], d["id"])
    print("Aggiunti {} documenti di seed.".format(len(seed)))

def pretty_print(rag_out):
    print("\n=== RISULTATO RAG ===")
    print("Grounded:", rag_out.get("grounded"))
    print("Conflicts:", rag_out.get("conflicts"))
    print("Citations:", rag_out.get("citations"))
    res = rag_out.get("results", [])
    print("TopK items:", len(res))
    if res:
        top = res[0]
        snippet = (top.get("text") or "")[:180].replace("\n", " ")
        print("Top[0] snippet:", snippet)

def main():
    km = KnowledgeManager(collection_name="fantacalcio_knowledge")
    ensure_seed_docs(km)

    texts, ids = dump_chroma_texts_ids(km.collection)
    rag = RAGPipeline(km.collection, texts, ids)

    qs = [
        "In che squadra gioca oggi Sandro Tonali?",
        "Conviene puntare su Koopmeiners all'asta?"
    ]
    for q in qs:
        print("\n--------------------------------------------")
        print("Query:", q)
        out = rag.retrieve(q, season="2025-26", final_k=8)
        pretty_print(out)

if __name__ == "__main__":
    main()
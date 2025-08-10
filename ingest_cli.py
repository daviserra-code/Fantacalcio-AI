# ingest_cli.py
# Ingest di file .jsonl nella collection Chroma + rebuild indici RAG
# Uso:
#   python ingest_cli.py --files data1.jsonl data2.jsonl
#   python ingest_cli.py --dir ./datasets/jsonl --reset
# Opzioni env supportate:
#   CHROMA_DB=./chroma_db   CHROMA_COLLECTION=fantacalcio_knowledge

import os
import sys
import glob
import argparse
from typing import List

from knowledge_manager import KnowledgeManager
from retrieval.helpers import dump_chroma_texts_ids
from retrieval.rag_pipeline import RAGPipeline

def find_jsonl_in_dir(d: str) -> List[str]:
    return sorted(glob.glob(os.path.join(d, "*.jsonl")))

def main():
    ap = argparse.ArgumentParser(description="Ingest JSONL in Chroma e rebuild RAG.")
    ap.add_argument("--files", nargs="*",
                    help="Lista di file .jsonl da caricare (formato: {id?, text, metadata?}).")
    ap.add_argument("--dir", type=str, default=None,
                    help="Cartella con file .jsonl (verranno presi tutti i .jsonl).")
    ap.add_argument("--reset", action="store_true",
                    help="Svuota il DB prima di caricare (ATTENZIONE: cancella tutto).")
    ap.add_argument("--collection", type=str, default=None,
                    help="Nome collection (override di CHROMA_COLLECTION).")
    ap.add_argument("--db-path", type=str, default=None,
                    help="Path DB Chroma (override di CHROMA_DB).")
    args = ap.parse_args()

    # Override env se passati da CLI
    if args.collection:
        os.environ["CHROMA_COLLECTION"] = args.collection
    if args.db_path:
        os.environ["CHROMA_DB"] = args.db_path

    # Raccogli i file
    files = args.files or []
    if args.dir:
        files.extend(find_jsonl_in_dir(args.dir))
    files = [f for f in files if f and os.path.exists(f)]

    if not files:
        print("Nessun file .jsonl trovato. Usa --files o --dir.")
        sys.exit(1)

    print("[CLI] Collection:", os.environ.get("CHROMA_COLLECTION", "fantacalcio_knowledge"))
    print("[CLI] DB path   :", os.environ.get("CHROMA_DB", "./chroma_db"))
    print("[CLI] Files     :", len(files))
    for f in files:
        print("  -", f)

    km = KnowledgeManager(collection_name=os.environ.get("CHROMA_COLLECTION", "fantacalcio_knowledge"))

    if args.reset:
        print("[CLI] Reset database...")
        if not km.reset_database():
            print("[CLI] Reset fallito, interrompo.")
            sys.exit(2)

    total = 0
    for f in files:
        print(f"[CLI] Ingest: {f}")
        added = km.load_from_jsonl(f)
        print(f"[CLI]   -> aggiunti: {added}")
        total += added

    # Ricostruisci RAG (BM25) dopo l’ingest
    try:
        texts, ids = dump_chroma_texts_ids(km.collection)
        rag = RAGPipeline(km.collection, texts, ids)
        print(f"[CLI] RAG ricostruito. Documenti indicizzati: {len(ids)}")
    except Exception as e:
        print("[CLI] Warning: ricostruzione RAG fallita:", e)

    print(f"[CLI] DONE. Totale documenti caricati: {total}. Count collection: {km.count()}")

if __name__ == "__main__":
    main()
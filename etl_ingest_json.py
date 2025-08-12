#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import glob
import json
import uuid
import logging
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.utils import embedding_functions

logging.basicConfig(level=logging.INFO, format="%(asctime)s - ingest - %(levelname)s - %(message)s")
log = logging.getLogger("ingest")

DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma")
COLL = os.getenv("CHROMA_COLLECTION", "fantacalcio_knowledge")
INPUT_DIR = os.getenv("KB_INPUT_DIR", "knowledge_base")
ST_MODEL = os.getenv("ST_MODEL", "all-MiniLM-L6-v2")

def load_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                log.warning("Riga non valida in %s: %s", path, e)
    return rows

def to_doc_and_meta(row: Dict[str, Any]) -> (str, Dict[str, Any]):
    """
    Costruisce il testo indicizzabile e i metadati da una riga JSON.
    Regole base:
      - 'text' o 'content' come corpo principale
      - metadati normalizzati per le query (type, league, season, player, team, role, source_date...)
    """
    text = row.get("text") or row.get("content") or ""
    if not text:
        # fallback ridotto da metadati, per non saltare l'item
        text = " ".join(str(v) for k, v in row.items() if isinstance(v, (str, int, float)) and k not in ("id",))

    meta = {
        "type": row.get("type"),
        "league": row.get("league") or "Serie A",
        "season": row.get("season") or os.getenv("SEASON", "2024-25"),
        "player": row.get("player"),
        "team": row.get("team"),
        "role": row.get("role"),
        "fantamedia": row.get("fantamedia"),
        "price": row.get("price"),
        "age": row.get("age"),
        "is_u21": row.get("is_u21"),
        "source": row.get("source"),
        "source_date": row.get("source_date"),
    }
    # pulizia None -> rimuovi chiavi vuote
    meta = {k: v for k, v in meta.items() if v is not None}
    return text, meta

def main():
    log.info("Ingest da: %s", INPUT_DIR)
    files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.jsonl")))
    if not files:
        log.warning("Nessun .jsonl trovato in %s", INPUT_DIR)
        return

    client = chromadb.PersistentClient(path=DB_PATH)
    # Preferisco usare embeddings lato Chroma con SentenceTransformer
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=ST_MODEL)

    coll = client.get_or_create_collection(
        name=COLL,
        metadata={"hnsw:space": "cosine"},
        embedding_function=emb_fn,
    )

    total_added = 0
    for fp in files:
        rows = load_jsonl(fp)
        if not rows:
            continue

        docs: List[str] = []
        metas: List[Dict[str, Any]] = []
        ids: List[str] = []
        for r in rows:
            doc, meta = to_doc_and_meta(r)
            if not doc.strip():
                continue
            docs.append(doc)
            metas.append(meta)
            rid = r.get("id") or str(uuid.uuid4())
            ids.append(rid)

        if docs:
            log.info("Indicizzo %s righe da %s…", len(docs), os.path.basename(fp))
            # per sicurezza, spezzetta in batch
            B = 256
            for i in range(0, len(docs), B):
                batch_docs = docs[i:i+B]
                batch_metas = metas[i:i+B]
                batch_ids = ids[i:i+B]
                coll.add(documents=batch_docs, metadatas=batch_metas, ids=batch_ids)
                total_added += len(batch_docs)

    log.info("Ingest completato. Aggiunti documenti: %s", total_added)
    # Stampa conteggio finale
    try:
        cnt = coll.count()
        log.info("Collection '%s' conteggio finale: %s", COLL, cnt)
    except Exception as e:
        log.warning("Impossibile leggere count: %s", e)

if __name__ == "__main__":
    main()

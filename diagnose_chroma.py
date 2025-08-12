#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import chromadb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - diag - %(levelname)s - %(message)s")
log = logging.getLogger("diag")

DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma")
COLL = os.getenv("CHROMA_COLLECTION", "fantacalcio_knowledge")

def main():
    log.info("CHROMA_DB_PATH=%s", DB_PATH)
    log.info("CHROMA_COLLECTION=%s", COLL)

    client = chromadb.PersistentClient(path=DB_PATH)

    cols = client.list_collections()
    if not cols:
        log.warning("Nessuna collezione trovata nel path indicato.")
    else:
        for c in cols:
            try:
                _c = client.get_collection(c.name)
                cnt = _c.count()
                log.info("Collection: %s -> %s items", c.name, cnt)
            except Exception as e:
                log.error("Errore su collection %s: %s", c.name, e)

    try:
        coll = client.get_or_create_collection(COLL)
        cnt = coll.count()
        log.info("Selezionata collection '%s' -> %s items", COLL, cnt)
    except Exception as e:
        log.error("Errore apertura collection selezionata: %s", e)

if __name__ == "__main__":
    main()

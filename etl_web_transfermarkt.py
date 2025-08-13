# etl_web_transfermarkt.py
# -*- coding: utf-8 -*-
import os
import time
import json
import logging
from typing import Dict, List

LOG = logging.getLogger("etl_web_transfermarkt")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", type=str, default="", help="Nome squadra (es. Juventus)")
    ap.add_argument("--season", type=str, default="2025-26")
    ap.add_argument("--write-roster", action="store_true")
    args = ap.parse_args()

    LOG.info("[ETL-WEB] Stub attivo — questa versione non effettua scraping live per evitare 429/ban.")
    LOG.info("[ETL-WEB] Team=%s season=%s", args.team, args.season)
    print(json.dumps({"ok": True, "items": []}, ensure_ascii=False))

if __name__ == "__main__":
    main()

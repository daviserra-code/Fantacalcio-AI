#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path

LOG_FMT = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
log = logging.getLogger("manage")

# --- Helper per import sicuri ---
def _safe_import_knowledge_manager():
    try:
        from knowledge_manager import KnowledgeManager
        return KnowledgeManager
    except Exception as e:
        log.error(f"Impossibile importare KnowledgeManager: {e}")
        sys.exit(1)

def _safe_import_etl_modules():
    etl_team = etl_league = None
    try:
        import etl_team_batch as etl_team  # opzionale
    except Exception as e:
        log.warning(f"etl_team_batch non disponibile: {e}")
    try:
        import etl_league_batch as etl_league  # opzionale
    except Exception as e:
        log.warning(f"etl_league_batch non disponibile: {e}")
    return etl_team, etl_league

# --- Percorsi ---
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# --- Commands ---
def cmd_kb_verify(args):
    KnowledgeManager = _safe_import_knowledge_manager()
    km = KnowledgeManager(
        collection_name=args.collection,
        persist_path=args.persist,
        embed_model=args.embed_model,
        device=args.device
    )
    # test embedding e query veloce
    count = km.count()
    log.info(f"[KB] Collection='{km.collection_name}', documents={count}")

    sample_q = args.sample_query or "fantacalcio trasferimento tonali"
    res = km.search_knowledge(sample_q, n_results=5)
    log.info(f"[KB] Query='{sample_q}' results={len(res)}")
    for i, r in enumerate(res):
        md = r.get("metadata", {})
        log.info(f"  {i+1:02d}. sim={r['relevance_score']:.3f} | {md.get('type','?')} | {md.get('player') or md.get('team') or ''}")

def cmd_kb_stats(args):
    KnowledgeManager = _safe_import_knowledge_manager()
    km = KnowledgeManager(
        collection_name=args.collection,
        persist_path=args.persist,
        embed_model=args.embed_model,
        device=args.device
    )
    count = km.count()
    log.info(f"[KB] Collection='{km.collection_name}' count={count}")
    # campionamento leggero
    res = km.search_knowledge("giocatore fantamedia stagione", n_results=10)
    types = {}
    seasons = {}
    for r in res:
        md = r.get("metadata", {})
        types[md.get("type","?")] = types.get(md.get("type","?"), 0) + 1
        seasons[md.get("season","?")] = seasons.get(md.get("season","?"), 0) + 1
    log.info(f"[KB] Types sample: {types}")
    log.info(f"[KB] Seasons sample: {seasons}")

def cmd_kb_vacuum(args):
    """
    Esporta tutta la collection in JSONL e ricrea pulito.
    ATTENZIONE: operazione distruttiva (ma con backup in exports/).
    """
    KnowledgeManager = _safe_import_knowledge_manager()

    # Forza ALLOW_KB_WRITES true per poter ricreare
    os.environ["ALLOW_KB_WRITES"] = "true"

    km = KnowledgeManager(
        collection_name=args.collection,
        persist_path=args.persist,
        embed_model=args.embed_model,
        device=args.device
    )
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_file = EXPORTS_DIR / f"{km.collection_name}_backup_{ts}.jsonl"

    log.info(f"[VACUUM] Esporto dati in {out_file} ...")
    # Chroma non ha iteratore nativo: facciamo una query “larga”
    # Nota: per dataset molto grandi, costruire un pager custom (ids slicing)
    dump = km.collection.get(include=["documents", "metadatas", "embeddings"])
    ids = dump.get("ids") or []
    docs = (dump.get("documents") or [])
    metas = (dump.get("metadatas") or [])
    n = len(ids)
    with out_file.open("w", encoding="utf-8") as f:
        for i in range(n):
            row = {
                "id": ids[i],
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info(f"[VACUUM] Backup completato: {n} record")

    log.info("[VACUUM] Resetto e ricreo la collection...")
    km.reset_database()

    log.info("[VACUUM] Reimport dal backup ...")
    reimported = km.load_from_jsonl(str(out_file))
    log.info(f"[VACUUM] Reimportati {reimported} record. Fatto.")

def cmd_etl_league(args):
    etl_team, etl_league = _safe_import_etl_modules()
    if not etl_league or not hasattr(etl_league, "run"):
        log.error("etl_league_batch.run non disponibile.")
        sys.exit(2)

    # Abilita scritture solo per la durata dell'ETL
    prev = os.environ.get("ALLOW_KB_WRITES", "false")
    os.environ["ALLOW_KB_WRITES"] = "true"
    try:
        stats = etl_league.run(
            league=args.league,
            season=args.season,
            collection=args.collection,
            persist=args.persist,
            limit=args.limit
        )
        log.info(f"[ETL-LEAGUE] Done: {stats}")
    finally:
        os.environ["ALLOW_KB_WRITES"] = prev

def cmd_etl_team(args):
    etl_team, etl_league = _safe_import_etl_modules()
    if not etl_team or not hasattr(etl_team, "run"):
        log.error("etl_team_batch.run non disponibile.")
        sys.exit(2)

    prev = os.environ.get("ALLOW_KB_WRITES", "false")
    os.environ["ALLOW_KB_WRITES"] = "true"
    try:
        stats = etl_team.run(
            team=args.team,
            season=args.season,
            collection=args.collection,
            persist=args.persist
        )
        log.info(f"[ETL-TEAM] Done: {stats}")
    finally:
        os.environ["ALLOW_KB_WRITES"] = prev

# --- Parser ---
def main():
    p = argparse.ArgumentParser(description="FantaCalcio-AI management CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # kb verify
    kbv = sub.add_parser("kb", help="KB utilities")
    kb_sub = kbv.add_subparsers(dest="kb_cmd", required=True)

    kb_verify = kb_sub.add_parser("verify", help="Verifica embedder/collection e fa una query di test")
    kb_verify.add_argument("--collection", default="fantacalcio_knowledge")
    kb_verify.add_argument("--persist", default="./chroma_db")
    kb_verify.add_argument("--embed-model", default="all-MiniLM-L6-v2")
    kb_verify.add_argument("--device", default="cpu")
    kb_verify.add_argument("--sample-query", default=None)
    kb_verify.set_defaults(func=cmd_kb_verify)

    kb_stats = kb_sub.add_parser("stats", help="Statistiche rapide su KB")
    kb_stats.add_argument("--collection", default="fantacalcio_knowledge")
    kb_stats.add_argument("--persist", default="./chroma_db")
    kb_stats.add_argument("--embed-model", default="all-MiniLM-L6-v2")
    kb_stats.add_argument("--device", default="cpu")
    kb_stats.set_defaults(func=cmd_kb_stats)

    kb_vacuum = kb_sub.add_parser("vacuum", help="Backup + reset + reimport della collection")
    kb_vacuum.add_argument("--collection", default="fantacalcio_knowledge")
    kb_vacuum.add_argument("--persist", default="./chroma_db")
    kb_vacuum.add_argument("--embed-model", default="all-MiniLM-L6-v2")
    kb_vacuum.add_argument("--device", default="cpu")
    kb_vacuum.set_defaults(func=cmd_kb_vacuum)

    # etl league
    etl_league = sub.add_parser("etl-league", help="Esegue ETL per una lega intera (batch)")
    etl_league.add_argument("--league", required=True, help='Es. "Serie A"')
    etl_league.add_argument("--season", required=True, help='Es. "2025-26"')
    etl_league.add_argument("--collection", default="fantacalcio_knowledge")
    etl_league.add_argument("--persist", default="./chroma_db")
    etl_league.add_argument("--limit", type=int, default=None, help="Limita squadre/processamenti (debug)")
    etl_league.set_defaults(func=cmd_etl_league)

    # etl team
    etl_team = sub.add_parser("etl-team", help="Esegue ETL per una singola squadra")
    etl_team.add_argument("--team", required=True, help='Es. "Inter"')
    etl_team.add_argument("--season", required=True, help='Es. "2025-26"')
    etl_team.add_argument("--collection", default="fantacalcio_knowledge")
    etl_team.add_argument("--persist", default="./chroma_db")
    etl_team.set_defaults(func=cmd_etl_team)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

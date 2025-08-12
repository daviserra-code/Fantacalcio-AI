# etl_runner.py
# -*- coding: utf-8 -*-

import os
import json
import time
import logging
import threading
import subprocess
from typing import Optional

LOG = logging.getLogger("etl_runner")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

_lock = threading.Lock()
_running = False


def _run(cmd: list, cwd: Optional[str] = None, timeout: Optional[int] = None) -> int:
    LOG.info("[ETL] Eseguo: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        start = time.time()
        while True:
            line = proc.stdout.readline()
            if line:
                LOG.info("[ETL] %s", line.rstrip())
            if proc.poll() is not None:
                break
            if timeout and (time.time() - start) > timeout:
                proc.kill()
                LOG.warning("[ETL] Timeout, processo terminato")
                return 124
        return proc.returncode or 0
    except FileNotFoundError:
        LOG.error("[ETL] Script non trovato: %s", cmd[0])
        return 127
    except Exception as e:
        LOG.error("[ETL] Errore esecuzione %s: %s", cmd, e)
        return 1


def _refresh_job():
    global _running
    try:
        LOG.info("[ETL] Refresh roster avviato (background)")
        # 1) prova ETL locale
        rc = _run(["python", "etl_build_roster.py"], timeout=600)
        # 2) se roster ancora vuoto e fallback abilitato, prova web serie A one-shot (se esiste lo script)
        roster_path = os.getenv("ROSTER_JSON_PATH", "./season_roster.json")
        need_web = True
        try:
            if os.path.exists(roster_path):
                with open(roster_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and len(data) > 20:
                    need_web = False
                elif isinstance(data, dict) and isinstance(data.get("players"), list) and len(data["players"]) > 20:
                    need_web = False
        except Exception:
            pass

        if need_web and os.path.exists("etl_web_transfermarkt_seriea.py"):
            LOG.info("[ETL] Provo fallback web one-shot Serie A…")
            _run(["python", "etl_web_transfermarkt_seriea.py", "--season", "2025-26", "--ingest", "--write-roster"], timeout=900)

        LOG.info("[ETL] Refresh roster completato")
    finally:
        _running = False


def start_background_refresh():
    """Avvia un refresh solo se non è già in corso."""
    global _running
    with _lock:
        if _running:
            LOG.info("[ETL] Refresh già in corso, non avvio un secondo job")
            return
        _running = True
        t = threading.Thread(target=_refresh_job, daemon=True)
        t.start()
        LOG.info("[ETL] Job di refresh lanciato")

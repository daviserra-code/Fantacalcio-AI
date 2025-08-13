# etl_runner.py
# -*- coding: utf-8 -*-
"""
Runner ETL in background per ricostruire il roster (season_roster.json).
Espone refresh_roster_async() usato da web_interface.py.

- Esegue per default: ETL_CMD="python etl_build_roster.py"
- Debounce/cooldown per evitare flood
- Logga ogni riga dello stdout dell'ETL con prefisso [ETL]
"""

import os
import shlex
import time
import logging
import threading
import subprocess
from typing import Optional, Dict

LOG = logging.getLogger("etl_runner")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

_ETL_LOCK = threading.Lock()
_IS_RUNNING = False
_LAST_START = 0.0


def _run_etl_once() -> None:
    """Esegue l'ETL una volta, catturando lo stdout e loggandolo riga per riga."""
    cmd = os.getenv("ETL_CMD", "python etl_build_roster.py")
    LOG.info("[ETL] Eseguo: %s", cmd)
    try:
        proc = subprocess.Popen(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
        )
    except Exception as e:
        LOG.error("[ETL] Avvio processo fallito: %s", e)
        return

    try:
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ""):
            LOG.info("[ETL] %s", line.rstrip("\n"))
        proc.wait()
        LOG.info("[ETL] Exit code: %s", proc.returncode)
    except Exception as e:
        LOG.error("[ETL] Errore in esecuzione: %s", e)


def refresh_roster_async(cooldown_sec: int = 60) -> bool:
    """
    Lancia l'ETL in un thread di background.
    Ritorna True se lancia davvero, False se è già in esecuzione o in cooldown.
    """
    global _IS_RUNNING, _LAST_START
    now = time.time()
    with _ETL_LOCK:
        if _IS_RUNNING:
            LOG.info("[ETL] Già in esecuzione, skip.")
            return False
        if now - _LAST_START < cooldown_sec:
            LOG.info("[ETL] In cooldown (%ds), skip.", cooldown_sec)
            return False

        _IS_RUNNING = True

        def _worker():
            global _IS_RUNNING, _LAST_START
            try:
                _run_etl_once()
            finally:
                with _ETL_LOCK:
                    _IS_RUNNING = False
                    _LAST_START = time.time()
                LOG.info("[ETL] Refresh roster completato")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        LOG.info("[ETL] Job di refresh lanciato (thread id=%s)", t.ident)
        return True


def refresh_roster_sync() -> None:
    """Versione sincrona (bloccante) dell'ETL."""
    global _IS_RUNNING, _LAST_START
    with _ETL_LOCK:
        if _IS_RUNNING:
            LOG.info("[ETL] Già in esecuzione; uscita senza lanciare doppione.")
            return
        _IS_RUNNING = True
    try:
        _run_etl_once()
    finally:
        with _ETL_LOCK:
            _IS_RUNNING = False
            _LAST_START = time.time()
        LOG.info("[ETL] Refresh roster completato (sync)")


def is_running() -> bool:
    with _ETL_LOCK:
        return _IS_RUNNING


def status() -> Dict[str, Optional[float]]:
    with _ETL_LOCK:
        return {"running": _IS_RUNNING, "last_start": _LAST_START}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ETL runner")
    parser.add_argument("--sync", action="store_true", help="Esegui in modo sincrono")
    parser.add_argument("--cooldown", type=int, default=60, help="Cooldown in secondi")
    args = parser.parse_args()

    if args.sync:
        refresh_roster_sync()
    else:
        launched = refresh_roster_async(cooldown_sec=args.cooldown)
        if launched:
            # attende finché il thread non termina
            while is_running():
                time.sleep(0.5)
        else:
            LOG.info("[ETL] Non lanciato (in esecuzione o in cooldown)")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
apify_transfermarkt_scraper.py
Integrazione con Apify per scraping Transfermarkt in modo professionale e affidabile.

Vantaggi:
- Bypass anti-bot e protezioni Transfermarkt
- Rate limiting gestito automaticamente
- Infrastruttura cloud scalabile
- Dataset strutturati e consistenti

Setup:
1. Registrati su https://apify.com
2. Ottieni API token da https://console.apify.com/account/integrations
3. Setta APIFY_API_TOKEN nelle secrets di Replit

Uso:
- python apify_transfermarkt_scraper.py --team "Juventus" --season "2025-26" --write-roster --ingest
- python apify_transfermarkt_scraper.py --all-serie-a --season "2025-26" --write-roster --ingest
"""

import os
import json
import time
import uuid
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import requests

# KnowledgeManager opzionale
try:
    from knowledge_manager import KnowledgeManager
    KM_AVAILABLE = True
except Exception:
    KM_AVAILABLE = False

LOG = logging.getLogger("apify_transfermarkt")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Configurazione Apify
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN")
APIFY_BASE_URL = "https://api.apify.com/v2"

# Actor IDs per diversi scraper Transfermarkt su Apify
# Usa il custom actor TransfermarktScraperDS (format: username~actor-name for private actors)
APIFY_ACTORS = {
    "transfermarkt_transfers": "yummy_pen~transfermarktscraperds",  # Custom Transfermarkt Scraper
    "transfermarkt_players": "yummy_pen~transfermarktscraperds",
}

# Mapping squadre Serie A -> URL Transfermarkt (simile a etl_tm_serie_a_full.py)
SERIE_A_TEAMS = {
    "Atalanta": "https://www.transfermarkt.it/atalanta-bergamo/transfers/verein/800",
    "Bologna": "https://www.transfermarkt.it/bologna-fc-1909/transfers/verein/1025",
    "Cagliari": "https://www.transfermarkt.it/cagliari-calcio/transfers/verein/1390",
    "Como": "https://www.transfermarkt.it/como-1907/transfers/verein/280",
    "Empoli": "https://www.transfermarkt.it/empoli-fc/transfers/verein/749",
    "Fiorentina": "https://www.transfermarkt.it/acf-fiorentina/transfers/verein/430",
    "Genoa": "https://www.transfermarkt.it/genoa-cfc/transfers/verein/252",
    "Inter": "https://www.transfermarkt.it/inter-mailand/transfers/verein/46",
    "Juventus": "https://www.transfermarkt.it/juventus-fc/transfers/verein/506",
    "Lazio": "https://www.transfermarkt.it/ss-lazio/transfers/verein/398",
    "Lecce": "https://www.transfermarkt.it/us-lecce/transfers/verein/1020",
    "Milan": "https://www.transfermarkt.it/ac-mailand/transfers/verein/5",
    "Monza": "https://www.transfermarkt.it/ac-monza/transfers/verein/2919",
    "Napoli": "https://www.transfermarkt.it/ssc-neapel/transfers/verein/6195",
    "Parma": "https://www.transfermarkt.it/parma-calcio-1913/transfers/verein/130",
    "Roma": "https://www.transfermarkt.it/as-roma/transfers/verein/12",
    "Torino": "https://www.transfermarkt.it/torino-fc/transfers/verein/416",
    "Udinese": "https://www.transfermarkt.it/udinese-calcio/transfers/verein/410",
    "Verona": "https://www.transfermarkt.it/hellas-verona/transfers/verein/276",
    "Venezia": "https://www.transfermarkt.it/venezia-fc/transfers/verein/907",
}


class ApifyTransfermarktScraper:
    """Client per scraping Transfermarkt tramite Apify"""

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or APIFY_API_TOKEN
        if not self.api_token:
            raise ValueError("APIFY_API_TOKEN richiesto. Configuralo nelle secrets di Replit.")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        })

    def run_actor(self, actor_id: str, input_data: Dict[str, Any], 
                  timeout_s: int = 300) -> Dict[str, Any]:
        """Esegue un actor Apify e attende i risultati"""

        # 1. Avvia il run
        run_url = f"{APIFY_BASE_URL}/acts/{actor_id}/runs"
        LOG.info("[APIFY] Avvio actor %s", actor_id)

        response = self.session.post(run_url, json=input_data)
        response.raise_for_status()
        run_data = response.json()

        run_id = run_data["data"]["id"]
        LOG.info("[APIFY] Run ID: %s", run_id)

        # 2. Attendi completamento
        status_url = f"{APIFY_BASE_URL}/actor-runs/{run_id}"
        start_time = time.time()

        while time.time() - start_time < timeout_s:
            response = self.session.get(status_url)
            response.raise_for_status()
            status_data = response.json()

            status = status_data["data"]["status"]
            LOG.info("[APIFY] Status: %s", status)

            if status == "SUCCEEDED":
                break
            elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                raise Exception(f"Actor run failed: {status}")

            time.sleep(5)  # Polling ogni 5 secondi
        else:
            raise TimeoutError(f"Actor run timeout dopo {timeout_s}s")

        # 3. Scarica dataset risultati
        dataset_id = status_data["data"]["defaultDatasetId"]
        dataset_url = f"{APIFY_BASE_URL}/datasets/{dataset_id}/items"

        response = self.session.get(dataset_url)
        response.raise_for_status()

        return {
            "run_id": run_id,
            "status": status,
            "items": response.json(),
            "stats": status_data["data"]["stats"]
        }

    def scrape_team_transfers(self, team: str, season: str = "2025-26",
                            arrivals_only: bool = False) -> List[Dict[str, Any]]:
        """Scrapa i trasferimenti di una squadra"""

        if team not in SERIE_A_TEAMS:
            raise ValueError(f"Squadra {team} non supportata")

        team_url = SERIE_A_TEAMS[team]

        # Input per il custom actor TransfermarktScraperDS
        actor_input = {
            "teamUrl": team_url,
            "season": season,
            "extractTransfers": True,
            "extractArrivals": not arrivals_only or True,
            "extractDepartures": not arrivals_only
        }

        LOG.info("[APIFY] Scraping %s transfers per stagione %s", team, season)

        try:
            result = self.run_actor(APIFY_ACTORS["transfermarkt_transfers"], actor_input)
            
            LOG.info("[APIFY] Actor returned %d raw items", len(result["items"]))

            # Trasforma i dati Apify nel formato compatibile con il tuo ETL
            transfers = []
            processed = 0
            skipped = 0
            
            for item in result["items"]:
                if isinstance(item, list):
                    # Se l'item è una lista di trasferimenti
                    for transfer_data in item:
                        processed += 1
                        transfer = self._normalize_transfer_data(transfer_data, team, season)
                        if transfer:
                            transfers.append(transfer)
                        else:
                            skipped += 1
                else:
                    # Se l'item è un singolo trasferimento
                    processed += 1
                    transfer = self._normalize_transfer_data(item, team, season)
                    if transfer:
                        transfers.append(transfer)
                    else:
                        skipped += 1

            LOG.info("[APIFY] %s: processati %d item, estratti %d trasferimenti, saltati %d", 
                     team, processed, len(transfers), skipped)
            return transfers

        except Exception as e:
            LOG.error("[APIFY] Errore scraping %s: %s", team, e)
            # Se l'actor specifico non esiste, suggerisci alternative
            if "404" in str(e) or "Not Found" in str(e):
                actor_id = APIFY_ACTORS["transfermarkt_transfers"]
                LOG.warning("[APIFY] L'actor %s non esiste o non è accessibile. Verifica:", actor_id)
                LOG.warning("[APIFY] 1. Il nome dell'actor è corretto: %s", actor_id)
                LOG.warning("[APIFY] 2. L'actor è pubblico o hai i permessi")
                LOG.warning("[APIFY] 3. Il token APIFY_API_TOKEN è valido")
                LOG.warning("[APIFY] 4. Usa il fallback diretto a Transfermarkt")
            return []

    def _normalize_transfer_data(self, raw_data: Dict[str, Any], 
                               team: str, season: str) -> Optional[Dict[str, Any]]:
        """Normalizza i dati Apify nel formato del tuo ETL"""

        try:
            # Il tuo actor già fornisce i dati strutturati correttamente
            player_name = raw_data.get("player")
            direction = raw_data.get("direction")  # Usa direttamente il campo dell'actor
            from_team = raw_data.get("from_team", "")
            to_team = raw_data.get("to_team", "")
            fee = raw_data.get("fee", "")
            
            # Il tuo actor già filtra per team, quindi non serve verificare nuovamente
            # Rimuoviamo il filtro che causava il problema dei "transfer 0"

            if not player_name or not direction:
                LOG.warning("[APIFY] Dati mancanti: player=%s, direction=%s", player_name, direction)
                return None

            result = {
                "id": f"apify_{uuid.uuid4().hex[:10]}",
                "type": "transfer",
                "season": season,
                "team": team,
                "player": player_name,
                "direction": direction,
                "from_team": from_team,
                "to_team": to_team,
                "fee": fee,
                "position": "",  # Non disponibile nei dati attuali
                "source": "apify_transfermarkt",
                "source_date": datetime.now().strftime("%Y-%m-%d"),
                "valid_from": datetime.now().strftime("%Y-%m-%d"),
                "valid_to": "2099-12-31",
                "apify_run_id": raw_data.get("_apify_run_id"),
                "scraped_at": raw_data.get("_apify_scraped_at")
            }
            
            LOG.debug("[APIFY] Normalized transfer: %s %s %s (%s)", player_name, from_team, to_team, direction)
            return result

        except Exception as e:
            LOG.warning("[APIFY] Errore normalizzazione dati: %s", e)
            LOG.warning("[APIFY] Raw data che ha causato errore: %s", raw_data)
            return None


def save_transfers_jsonl(transfers: List[Dict[str, Any]], team: str, season: str) -> Path:
    """Salva i trasferimenti in formato JSONL"""

    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)

    slug = team.lower().replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"apify_transfers_{slug}_{season.replace('/', '-')}_{timestamp}.jsonl"
    filepath = data_dir / filename

    with filepath.open("w", encoding="utf-8") as f:
        for transfer in transfers:
            f.write(json.dumps(transfer, ensure_ascii=False) + "\n")

    LOG.info("[EXPORT] Salvato %s con %d trasferimenti", filepath, len(transfers))
    return filepath


def merge_into_roster(transfers: List[Dict[str, Any]], roster_path: Path = Path("./season_roster.json")) -> int:
    """Aggiorna season_roster.json con i nuovi arrivi (stesso formato di etl_tm_serie_a_full.py)"""

    try:
        with roster_path.open("r", encoding="utf-8") as f:
            roster = json.load(f)
    except Exception:
        roster = []

    # Indicizza roster esistente
    roster_index = {}
    for player in roster:
        key = (player.get("name", "").lower(), player.get("team", "").lower())
        roster_index[key] = player

    updates = 0
    for transfer in transfers:
        if transfer.get("direction") != "in":
            continue  # Solo arrivi nel roster

        name = transfer.get("player", "")
        team = transfer.get("team", "")
        if not name or not team:
            continue

        key = (name.lower(), team.lower())

        if key not in roster_index:
            # Nuovo giocatore
            roster.append({
                "name": name,
                "team": team,
                "role": transfer.get("position") or "NA",
                "season": transfer.get("season"),
                "type": "current_player",
                "source": transfer.get("source"),
                "source_date": transfer.get("source_date"),
            })
            updates += 1
        else:
            # Aggiorna esistente
            player = roster_index[key]
            player["season"] = transfer.get("season")
            player["source"] = transfer.get("source")
            player["source_date"] = transfer.get("source_date")
            updates += 1

    with roster_path.open("w", encoding="utf-8") as f:
        json.dump(roster, f, ensure_ascii=False, indent=2)

    LOG.info("[ROSTER] Aggiornati %d giocatori, totale roster: %d", updates, len(roster))
    return updates


def ingest_into_kb(transfers: List[Dict[str, Any]]) -> int:
    """Inserisce i trasferimenti nella Knowledge Base (compatibile con etl_tm_serie_a_full.py)"""

    if not KM_AVAILABLE:
        LOG.warning("[INGEST] KnowledgeManager non disponibile")
        return 0

    try:
        km = KnowledgeManager()
        docs, metas, ids = [], [], []

        for transfer in transfers:
            direction_str = "IN" if transfer.get("direction") == "in" else "OUT"

            # Documento testuale
            docs.append(
                f"Transfer {direction_str}: {transfer.get('player')} "
                f"{'→' if direction_str=='IN' else '←'} {transfer.get('team')} ({transfer.get('season')}). "
                f"From: {transfer.get('from_team', 'n/a')} To: {transfer.get('to_team', 'n/a')}. "
                f"Fee: {transfer.get('fee', 'n/a')}. Source: Apify Transfermarkt."
            )

            # Metadati
            metas.append({
                "type": "transfer",
                "player": transfer.get("player"),
                "team": transfer.get("team"),
                "season": transfer.get("season"),
                "direction": transfer.get("direction"),
                "from_team": transfer.get("from_team", ""),
                "to_team": transfer.get("to_team", ""),
                "fee": transfer.get("fee", ""),
                "position": transfer.get("position", ""),
                "source": transfer.get("source"),
                "source_date": transfer.get("source_date"),
                "valid_from": transfer.get("valid_from"),
                "valid_to": transfer.get("valid_to"),
                "apify_run_id": transfer.get("apify_run_id"),
            })

            ids.append(transfer.get("id") or f"apify_{uuid.uuid4().hex[:10]}")

        n = km.upsert(docs=docs, metadatas=metas, ids=ids)
        LOG.info("[INGEST] Inseriti %s trasferimenti in KB", n)
        return int(n or 0)

    except Exception as e:
        LOG.error("[INGEST] Errore: %s", e)
        return 0


def main():
    parser = argparse.ArgumentParser(description="Apify Transfermarkt Scraper per Fantasy Football")
    parser.add_argument("--team", help="Nome squadra (es. Juventus)")
    parser.add_argument("--all-serie-a", action="store_true", help="Scrapa tutte le squadre Serie A")
    parser.add_argument("--season", default="2025-26", help="Stagione (default: 2025-26)")
    parser.add_argument("--arrivals-only", action="store_true", help="Solo arrivi (default: arrivi+cessioni)")
    parser.add_argument("--write-roster", action="store_true", help="Aggiorna season_roster.json")
    parser.add_argument("--ingest", action="store_true", help="Inserisci in Knowledge Base")
    parser.add_argument("--delay", type=float, default=5.0, help="Delay tra squadre (secondi)")

    args = parser.parse_args()

    if not args.team and not args.all_serie_a:
        parser.error("Specifica --team NOME oppure --all-serie-a")

    # Verifica token Apify
    if not APIFY_API_TOKEN:
        LOG.error("APIFY_API_TOKEN non configurato. Vai su https://console.apify.com/account/integrations")
        return 1

    scraper = ApifyTransfermarktScraper()
    all_transfers = []

    teams_to_process = [args.team] if args.team else list(SERIE_A_TEAMS.keys())

    for i, team in enumerate(teams_to_process, 1):
        LOG.info("(%d/%d) Processando %s", i, len(teams_to_process), team)

        try:
            transfers = scraper.scrape_team_transfers(
                team=team,
                season=args.season,
                arrivals_only=args.arrivals_only
            )

            if transfers:
                # Salva JSONL per ogni squadra
                save_transfers_jsonl(transfers, team, args.season)
                all_transfers.extend(transfers)
            else:
                LOG.warning("Nessun trasferimento trovato per %s", team)

        except Exception as e:
            LOG.error("Errore processando %s: %s", team, e)

        # Delay tra squadre per non sovraccaricare Apify
        if i < len(teams_to_process):
            time.sleep(args.delay)

    # Operazioni finali
    if all_transfers:
        # Salva file combinato
        combined_path = save_transfers_jsonl(all_transfers, "SERIE_A_COMBINED", args.season)
        LOG.info("File combinato: %s", combined_path)

        # Aggiorna roster
        if args.write_roster:
            merge_into_roster(all_transfers)

        # Inserisci in KB
        if args.ingest:
            ingest_into_kb(all_transfers)

    LOG.info("Completato! Trasferimenti totali: %d", len(all_transfers))


if __name__ == "__main__":
    main()
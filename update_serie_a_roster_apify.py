
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
update_serie_a_roster_apify.py
Dedicated script to update the entire Serie A roster using Apify integration.

Usage:
    python update_serie_a_roster_apify.py --season 2025-26
    python update_serie_a_roster_apify.py --season 2025-26 --arrivals-only
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Import the existing Apify scraper
from apify_transfermarkt_scraper import ApifyTransfermarktScraper, merge_into_roster, ingest_into_kb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

LOG = logging.getLogger("serie_a_roster_update")

def update_complete_roster(season: str = "2025-26", arrivals_only: bool = False):
    """Update the complete Serie A roster using Apify"""
    
    # Check if Apify is configured
    if not os.environ.get("APIFY_API_TOKEN"):
        LOG.error("APIFY_API_TOKEN not configured. Please set it in Replit Secrets.")
        return False
    
    try:
        scraper = ApifyTransfermarktScraper()
        all_transfers = []
        
        # Serie A teams from the existing mapping
        from apify_transfermarkt_scraper import SERIE_A_TEAMS
        teams = list(SERIE_A_TEAMS.keys())
        
        LOG.info(f"Starting Serie A roster update for season {season}")
        LOG.info(f"Processing {len(teams)} teams...")
        
        for i, team in enumerate(teams, 1):
            LOG.info(f"({i}/{len(teams)}) Processing {team}...")
            
            try:
                transfers = scraper.scrape_team_transfers(
                    team=team,
                    season=season,
                    arrivals_only=arrivals_only
                )
                
                if transfers:
                    all_transfers.extend(transfers)
                    LOG.info(f"{team}: {len(transfers)} transfers found")
                else:
                    LOG.warning(f"{team}: No transfers found")
                    
            except Exception as e:
                LOG.error(f"Error processing {team}: {e}")
                continue
            
            # Rate limiting - be respectful to Apify
            import time
            time.sleep(3.0)
        
        if not all_transfers:
            LOG.warning("No transfers found for any team")
            return False
        
        LOG.info(f"Total transfers collected: {len(all_transfers)}")
        
        # Update roster with arrivals only
        arrivals = [t for t in all_transfers if t.get("direction") == "in"]
        if arrivals:
            roster_updates = merge_into_roster(arrivals, Path("./season_roster.json"))
            LOG.info(f"Roster updated: {roster_updates} players")
        
        # Ingest all transfers into Knowledge Base
        kb_updates = ingest_into_kb(all_transfers)
        LOG.info(f"Knowledge Base updated: {kb_updates} entries")
        
        LOG.info("Serie A roster update completed successfully!")
        return True
        
    except Exception as e:
        LOG.error(f"Failed to update Serie A roster: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Update Serie A roster via Apify")
    parser.add_argument("--season", default="2025-26", help="Season (e.g., 2025-26)")
    parser.add_argument("--arrivals-only", action="store_true", help="Only process arrivals")
    
    args = parser.parse_args()
    
    success = update_complete_roster(
        season=args.season,
        arrivals_only=args.arrivals_only
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

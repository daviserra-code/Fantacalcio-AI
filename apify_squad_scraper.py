#!/usr/bin/env python3
"""
Hybrid squad page scraper for position extraction
Uses Apify Web Scraper to extract positions from Transfermarkt squad pages
Cost-effective solution for the 329 players with Role: "NA"
"""

import json
import os
import logging
import time
from pathlib import Path
from typing import Dict, List, Any
import requests
from datetime import datetime
import re
import unicodedata

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOG = logging.getLogger(__name__)

# Position mapping from Transfermarkt to Fantasy Football roles
POSITION_MAPPING = {
    # Goalkeeper
    "Goalkeeper": "P", "GK": "P", "Portiere": "P", "TW": "P",
    
    # Defender  
    "Centre-Back": "D", "Left-Back": "D", "Right-Back": "D", "Defender": "D",
    "Central Defender": "D", "Left Defender": "D", "Right Defender": "D",
    "Difensore": "D", "Difensore centrale": "D", "Terzino": "D", 
    "Terzino sinistro": "D", "Terzino destro": "D", "LB": "D", "RB": "D", "CB": "D", "IV": "D",
    # German abbreviations for defenders
    "LV": "D", "RV": "D", "ZIV": "D",  # Left/Right/Central Defender
    
    # Midfielder 
    "Central Midfield": "C", "Defensive Midfield": "C", "Attacking Midfield": "C",
    "Left Midfield": "C", "Right Midfield": "C", "Midfielder": "C",
    "Centrocampista": "C", "Mediano": "C", "Trequartista": "C",
    "Centrocampista centrale": "C", "Esterno centrocampo": "C",
    "CM": "C", "CDM": "C", "CAM": "C", "LM": "C", "RM": "C", "DM": "C", "AM": "C",
    "Mezzala": "C", "Esterno destro": "C", "Esterno sinistro": "C",
    # German abbreviations for midfielders
    "ZM": "C", "OM": "C", "ZOM": "C", "DM": "C", "AM": "C",  # Central/Offensive/Defensive Midfielder
    
    # Wing-back (usually counted as Defender in Fantasy)
    "Left-Back": "D", "Right-Back": "D", "Wing-Back": "D", "LWB": "D", "RWB": "D",
    
    # Forward/Attacker
    "Centre-Forward": "A", "Left Winger": "A", "Right Winger": "A", 
    "Striker": "A", "Forward": "A", "Attacker": "A",
    "Attaccante": "A", "Punta": "A", "Ala": "A", "Esterno offensivo": "A",
    "Prima punta": "A", "Seconda punta": "A", "Second Striker": "A",
    "CF": "A", "LW": "A", "RW": "A", "ST": "A", "SS": "A",
    "Ala sinistra": "A", "Ala destra": "A",
    # German abbreviations for forwards/wingers  
    "MS": "A", "LA": "A", "RA": "A", "ZS": "A",  # Striker/Left/Right Wing/Central Forward
}

# Serie A teams with squad URLs
SERIE_A_SQUAD_URLS = {
    "Atalanta": "https://www.transfermarkt.it/atalanta-bergamo/kader/verein/800/saison_id/2025",
    "Bologna": "https://www.transfermarkt.it/bologna-fc-1909/kader/verein/1025/saison_id/2025", 
    "Cagliari": "https://www.transfermarkt.it/cagliari-calcio/kader/verein/1390/saison_id/2025",
    "Como": "https://www.transfermarkt.it/como-1907/kader/verein/280/saison_id/2025",
    "Empoli": "https://www.transfermarkt.it/empoli-fc/kader/verein/749/saison_id/2025",
    "Fiorentina": "https://www.transfermarkt.it/acf-fiorentina/kader/verein/430/saison_id/2025",
    "Genoa": "https://www.transfermarkt.it/genoa-cfc/kader/verein/252/saison_id/2025",
    "Inter": "https://www.transfermarkt.it/inter-mailand/kader/verein/46/saison_id/2025",
    "Juventus": "https://www.transfermarkt.it/juventus-fc/kader/verein/506/saison_id/2025",
    "Lazio": "https://www.transfermarkt.it/ss-lazio/kader/verein/398/saison_id/2025",
    "Lecce": "https://www.transfermarkt.it/us-lecce/kader/verein/1020/saison_id/2025",
    "Milan": "https://www.transfermarkt.it/ac-mailand/kader/verein/5/saison_id/2025",
    "Monza": "https://www.transfermarkt.it/ac-monza/kader/verein/2919/saison_id/2025",
    "Napoli": "https://www.transfermarkt.it/ssc-neapel/kader/verein/6195/saison_id/2025",
    "Parma": "https://www.transfermarkt.it/parma-calcio-1913/kader/verein/130/saison_id/2025",
    "Roma": "https://www.transfermarkt.it/as-roma/kader/verein/12/saison_id/2025",
    "Torino": "https://www.transfermarkt.it/torino-fc/kader/verein/416/saison_id/2025",
    "Udinese": "https://www.transfermarkt.it/udinese-calcio/kader/verein/410/saison_id/2025",
    "Verona": "https://www.transfermarkt.it/hellas-verona/kader/verein/276/saison_id/2025",
    "Venezia": "https://www.transfermarkt.it/venezia-fc/kader/verein/907/saison_id/2025"
}

def normalize_name(name: str) -> str:
    """Normalize player name for matching (remove accents, lowercase, etc.)"""
    if not name:
        return ""
    
    # Remove accents
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    
    # Convert to lowercase and remove extra spaces
    name = re.sub(r'\s+', ' ', name.lower().strip())
    
    return name

def map_position_to_role(position: str) -> str:
    """Convert Transfermarkt position to Fantasy Football role (P/D/C/A)"""
    if not position:
        return "NA"
    
    # Clean and normalize position string
    position_clean = position.strip().title()
    
    # Direct mapping first
    if position_clean in POSITION_MAPPING:
        return POSITION_MAPPING[position_clean]
    
    # Fuzzy matching for partial strings
    position_lower = position.lower()
    for key, role in POSITION_MAPPING.items():
        if key.lower() in position_lower or position_lower in key.lower():
            return role
    
    # Default fallback
    return "NA"

class ApifySquadScraper:
    """Scraper for Transfermarkt squad pages using Apify Web Scraper"""
    
    def __init__(self):
        self.api_token = os.getenv("APIFY_API_TOKEN")
        if not self.api_token:
            raise ValueError("APIFY_API_TOKEN environment variable required")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        })
    
    def create_squad_scraper_config(self) -> Dict[str, Any]:
        """Create Apify Web Scraper configuration for squad pages"""
        
        # Build start URLs for all Serie A teams with team names in userData
        start_urls = []
        for team_name, url in SERIE_A_SQUAD_URLS.items():
            start_urls.append({
                "url": url,
                "userData": {"team": team_name}
            })
        
        # Page function to extract player data from squad tables
        page_function = """
        async function pageFunction(context) {
            const { page, request } = context;
            
            // Wait for squad table to load
            await page.waitForSelector('.items tbody tr', { timeout: 15000 });
            
            // Get team name from userData
            const teamName = request.userData?.team || 'unknown';
            
            // Extract player data from table
            const players = await page.evaluate(() => {
                const rows = document.querySelectorAll('.items tbody tr');
                const results = [];
                
                // First, find the position column index by checking headers
                const headers = document.querySelectorAll('.items thead th');
                let positionColumnIndex = -1;
                
                headers.forEach((header, index) => {
                    const headerText = header.textContent.trim().toLowerCase();
                    if (headerText.includes('pos') || headerText.includes('position')) {
                        positionColumnIndex = index;
                    }
                });
                
                // Fallback: assume position is in column 2 (common for Transfermarkt)
                if (positionColumnIndex === -1) positionColumnIndex = 1;
                
                rows.forEach(row => {
                    const nameCell = row.querySelector('.hauptlink a');
                    const cells = row.querySelectorAll('td');
                    
                    if (nameCell && cells.length > positionColumnIndex) {
                        const name = nameCell.textContent.trim();
                        const position = cells[positionColumnIndex].textContent.trim();
                        
                        if (name && position && name !== 'Name') {
                            results.push({
                                name: name,
                                position: position
                            });
                        }
                    }
                });
                
                return results;
            });
            
            // Add team name to each player
            return players.map(player => ({
                ...player,
                team: teamName,
                source_url: request.url
            }));
        }
        """
        
        return {
            "startUrls": start_urls,
            "pageFunction": page_function,
            "maxRequestsPerCrawl": 20,
            "maxConcurrency": 2,
            "requestTimeoutSecs": 60
        }
    
    def run_squad_scraper(self) -> List[Dict[str, Any]]:
        """Run Apify Web Scraper on all Serie A squad pages"""
        
        LOG.info("🕷️ Starting squad page scraping for all Serie A teams...")
        
        config = self.create_squad_scraper_config()
        
        # Use Apify's Web Scraper actor
        response = self.session.post(
            "https://api.apify.com/v2/acts/apify~web-scraper/runs",
            json=config
        )
        response.raise_for_status()
        run_data = response.json()
        
        run_id = run_data["data"]["id"]
        LOG.info(f"🚀 Squad scraper started, run ID: {run_id}")
        
        # Wait for completion
        timeout = 300  # 5 minutes
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < timeout:
            status_response = self.session.get(f"https://api.apify.com/v2/actor-runs/{run_id}")
            status_response.raise_for_status()
            status = status_response.json()["data"]["status"]
            
            LOG.info(f"📊 Squad scraper status: {status}")
            
            if status == "SUCCEEDED":
                break
            elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                raise RuntimeError(f"Squad scraper failed with status: {status}")
            
            time.sleep(10)
        else:
            raise TimeoutError("Squad scraper timeout")
        
        # Get results
        dataset_id = status_response.json()["data"]["defaultDatasetId"]
        results_response = self.session.get(f"https://api.apify.com/v2/datasets/{dataset_id}/items")
        results_response.raise_for_status()
        
        players = results_response.json()
        LOG.info(f"✅ Squad scraper completed, extracted {len(players)} players")
        
        return players

def backfill_positions_from_squads(dry_run: bool = True) -> Dict[str, int]:
    """Backfill positions using squad page data"""
    
    LOG.info("🔄 Starting position backfill using squad page data...")
    
    # Load current roster
    roster_path = Path("season_roster.json")
    with roster_path.open("r", encoding="utf-8") as f:
        roster = json.load(f)
    
    # Get NA players from apify_transfermarkt source
    na_players = [p for p in roster if p.get("role") == "NA" and p.get("source") == "apify_transfermarkt"]
    LOG.info(f"Found {len(na_players)} players with Role: NA")
    
    # Run squad scraper
    scraper = ApifySquadScraper()
    squad_players = scraper.run_squad_scraper()
    
    LOG.info(f"Extracted {len(squad_players)} players from squad pages")
    
    # Create lookup by team + normalized name
    stats = {"updated": 0, "unchanged": 0, "errors": 0}
    
    for player in na_players:
        try:
            name = player.get("name", "")
            team = player.get("team", "")
            
            if not name or not team:
                stats["unchanged"] += 1
                continue
            
            # Find matching squad player by team and name
            name_norm = normalize_name(name)
            squad_player = None
            
            # Look for exact team match first
            for sp in squad_players:
                if (sp.get("team", "").lower() == team.lower() and 
                    normalize_name(sp.get("name", "")) == name_norm):
                    squad_player = sp
                    break
            
            if squad_player:
                position = squad_player.get("position", "")
                new_role = map_position_to_role(position)
                
                if new_role != "NA":
                    LOG.info(f"✅ {name} ({team}): {position} → {new_role}")
                    if not dry_run:
                        player["role"] = new_role
                        player["position"] = position
                        player["source_date"] = datetime.now().strftime("%Y-%m-%d")
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
            else:
                LOG.debug(f"❓ {name} ({team}) not found in squad data")
                stats["unchanged"] += 1
                
        except Exception as e:
            LOG.error(f"❌ Error processing {name}: {e}")
            stats["errors"] += 1
    
    if not dry_run:
        # Save updated roster
        with roster_path.open("w", encoding="utf-8") as f:
            json.dump(roster, f, ensure_ascii=False, indent=2)
        LOG.info(f"💾 Updated roster saved to {roster_path}")
    
    LOG.info(f"📊 Results: {stats['updated']} updated, {stats['unchanged']} unchanged, {stats['errors']} errors")
    return stats

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill positions using squad pages")
    parser.add_argument("--dry-run", action="store_true", help="Run without making changes")
    parser.add_argument("--apply", action="store_true", help="Apply changes to roster")
    
    args = parser.parse_args()
    
    if args.apply:
        backfill_positions_from_squads(dry_run=False)
    else:
        backfill_positions_from_squads(dry_run=True)
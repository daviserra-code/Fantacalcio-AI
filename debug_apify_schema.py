#!/usr/bin/env python3
"""
Debug script to examine raw Apify output and find where position data is stored
"""

import json
import logging
from apify_transfermarkt_scraper import ApifyTransfermarktScraper

logging.basicConfig(level=logging.INFO)

def debug_apify_output():
    """Debug the raw output from Apify actor to find position data"""
    
    scraper = ApifyTransfermarktScraper()
    
    print("🔍 Running Apify actor with enhanced position extraction...")
    
    try:
        # Get raw result from actor
        team_url = "https://www.transfermarkt.it/genoa-cfc/transfers/verein/252"
        actor_input = {
            "teamUrl": team_url,
            "season": "2025-26",
            "extractTransfers": True,
            "extractArrivals": True,
            "extractDepartures": False,
            "extractPlayerPositions": True,
            "includePlayerDetails": True
        }
        
        result = scraper.run_actor("yummy_pen~transfermarktscraperds", actor_input)
        
        print(f"✅ Actor returned {len(result['items'])} raw items")
        
        # Examine first few raw items to see structure
        print("\n🔍 Examining raw data structure:")
        for i, item in enumerate(result['items'][:3]):
            print(f"\n--- Raw Item {i+1} ---")
            print(json.dumps(item, indent=2, ensure_ascii=False)[:500] + "...")
            
            # Look for any position-related fields
            if isinstance(item, dict):
                position_fields = [k for k in item.keys() if any(pos in k.lower() for pos in ['position', 'role', 'pos', 'ruolo'])]
                if position_fields:
                    print(f"🎯 Found position-related fields: {position_fields}")
                    for field in position_fields:
                        print(f"  {field}: {item[field]}")
                else:
                    print("❌ No position-related fields found")
            
        return result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    debug_apify_output()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
debug_apify_structure.py
Script per analizzare la struttura dati del tuo actor Apify personalizzato
"""

import os
import json
import logging
from apify_transfermarkt_scraper import ApifyTransfermarktScraper

logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger("debug_apify")

def debug_actor_output():
    """Analizza l'output del tuo actor per una squadra di test"""
    
    if not os.environ.get("APIFY_API_TOKEN"):
        print("❌ APIFY_API_TOKEN non configurato")
        return
    
    try:
        scraper = ApifyTransfermarktScraper()
        
        # Test con una squadra
        test_team = "Juventus"
        LOG.info(f"Testing con {test_team}...")
        
        # Chiamata diretta all'actor
        team_url = "https://www.transfermarkt.it/juventus-fc/transfers/verein/506"
        actor_input = {
            "teamUrl": team_url,
            "season": "2025-26",
            "extractTransfers": True,
            "extractArrivals": True,
            "extractDepartures": True
        }
        
        result = scraper.run_actor("yummy_pen~transfermarktscraperds", actor_input)
        
        print(f"\n🔍 RISULTATI ACTOR:")
        print(f"Status: {result.get('status')}")
        print(f"Items count: {len(result.get('items', []))}")
        
        items = result.get("items", [])
        if items:
            print(f"\n📋 PRIMI 3 ITEMS:")
            for i, item in enumerate(items[:3]):
                print(f"\n--- Item {i+1} ---")
                if isinstance(item, dict):
                    print("Chiavi disponibili:", list(item.keys()))
                    for key, value in list(item.items())[:10]:  # Prime 10 chiavi
                        print(f"  {key}: {value}")
                else:
                    print(f"Tipo: {type(item)}, Valore: {item}")
            
            # Salva sample per analisi
            with open("debug_apify_sample.json", "w", encoding="utf-8") as f:
                json.dump(items[:10], f, indent=2, ensure_ascii=False)
            print(f"\n💾 Sample salvato in debug_apify_sample.json")
        
        # Test normalizzazione
        print(f"\n🔄 TEST NORMALIZZAZIONE:")
        transfers = scraper.scrape_team_transfers(test_team, "2025-26", arrivals_only=False)
        print(f"Transfers normalizzati: {len(transfers)}")
        
        if transfers:
            print("Primo transfer normalizzato:")
            print(json.dumps(transfers[0], indent=2, ensure_ascii=False))
            
            arrivals = [t for t in transfers if t.get("direction") == "in"]
            departures = [t for t in transfers if t.get("direction") == "out"]
            print(f"Arrivi: {len(arrivals)}, Partenze: {len(departures)}")
        
    except Exception as e:
        LOG.error(f"Errore durante debug: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_actor_output()

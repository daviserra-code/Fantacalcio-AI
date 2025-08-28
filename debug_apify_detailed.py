
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
from apify_transfermarkt_scraper import ApifyTransfermarktScraper

logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger("debug_apify_detailed")

def analyze_raw_data():
    """Analizza in dettaglio i dati raw dell'actor"""
    
    if not os.environ.get("APIFY_API_TOKEN"):
        print("❌ APIFY_API_TOKEN non configurato")
        return
    
    try:
        scraper = ApifyTransfermarktScraper()
        
        # Input per Juventus
        team_url = "https://www.transfermarkt.it/juventus-fc/transfers/verein/506"
        actor_input = {
            "teamUrl": team_url,
            "season": "2025-26",
            "extractTransfers": True,
            "extractArrivals": True,
            "extractDepartures": True
        }
        
        print("🔄 Chiamata diretta all'actor...")
        result = scraper.run_actor("yummy_pen~transfermarktscraperds", actor_input)
        
        items = result.get("items", [])
        print(f"📊 Total items: {len(items)}")
        
        if items:
            # Analizza il primo item in dettaglio
            first_item = items[0]
            print(f"\n🔍 PRIMO ITEM:")
            print(f"Tipo: {type(first_item)}")
            
            if isinstance(first_item, dict):
                print("Chiavi disponibili:")
                for key, value in first_item.items():
                    print(f"  {key}: {value} (tipo: {type(value)})")
            elif isinstance(first_item, list):
                print(f"Lista di {len(first_item)} elementi")
                if first_item:
                    print("Primo elemento della lista:")
                    print(f"  Tipo: {type(first_item[0])}")
                    if isinstance(first_item[0], dict):
                        print("  Chiavi:", list(first_item[0].keys()))
            
            # Salva tutti i dati per ispezione
            with open("debug_apify_raw_data.json", "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False, default=str)
            print(f"💾 Dati raw salvati in debug_apify_raw_data.json")
            
            # Prova normalizzazione su primi 5 item
            print(f"\n🔧 TEST NORMALIZZAZIONE:")
            for i, item in enumerate(items[:5]):
                try:
                    if isinstance(item, dict):
                        transfer = scraper._normalize_transfer_data(item, "Juventus", "2025-26")
                        if transfer:
                            print(f"✅ Item {i}: {transfer['player']} ({transfer['direction']})")
                        else:
                            print(f"❌ Item {i}: Normalizzazione fallita")
                            print(f"   Dati: {item}")
                    elif isinstance(item, list):
                        print(f"📋 Item {i}: Lista di {len(item)} elementi")
                        for j, sub_item in enumerate(item[:3]):
                            if isinstance(sub_item, dict):
                                transfer = scraper._normalize_transfer_data(sub_item, "Juventus", "2025-26")
                                if transfer:
                                    print(f"✅   Sub-item {j}: {transfer['player']} ({transfer['direction']})")
                                else:
                                    print(f"❌   Sub-item {j}: Normalizzazione fallita")
                except Exception as e:
                    print(f"❌ Errore item {i}: {e}")
        
    except Exception as e:
        LOG.error(f"Errore durante debug: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_raw_data()

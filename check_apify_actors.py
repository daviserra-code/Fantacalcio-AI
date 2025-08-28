
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script per verificare gli actor Apify disponibili e trovare alternative
per il scraping di Transfermarkt.
"""

import os
import requests
import logging

LOG = logging.getLogger("apify_check")
logging.basicConfig(level=logging.INFO)

APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN")
APIFY_BASE_URL = "https://api.apify.com/v2"

def check_actor_exists(actor_id: str) -> bool:
    """Verifica se un actor esiste"""
    if not APIFY_API_TOKEN:
        print("❌ APIFY_API_TOKEN non configurato")
        return False
    
    headers = {"Authorization": f"Bearer {APIFY_API_TOKEN}"}
    url = f"{APIFY_BASE_URL}/acts/{actor_id}"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            actor_data = response.json()
            print(f"✅ Actor {actor_id} trovato: {actor_data['data']['name']}")
            return True
        elif response.status_code == 404:
            print(f"❌ Actor {actor_id} non trovato (404)")
            return False
        else:
            print(f"⚠️  Actor {actor_id}: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Errore controllando {actor_id}: {e}")
        return False

def search_transfermarkt_actors():
    """Cerca actors disponibili per Transfermarkt"""
    if not APIFY_API_TOKEN:
        print("❌ APIFY_API_TOKEN non configurato")
        return
    
    headers = {"Authorization": f"Bearer {APIFY_API_TOKEN}"}
    url = f"{APIFY_BASE_URL}/store"
    
    try:
        # Cerca nel marketplace
        search_params = {
            "search": "transfermarkt",
            "limit": 10
        }
        
        response = requests.get(url, headers=headers, params=search_params)
        if response.status_code == 200:
            store_data = response.json()
            actors = store_data.get("data", {}).get("items", [])
            
            if actors:
                print(f"\n🔍 Trovati {len(actors)} actors per 'transfermarkt':")
                for actor in actors:
                    print(f"  - {actor['id']}: {actor['title']}")
                    print(f"    Descrizione: {actor.get('description', 'N/A')[:100]}...")
                    print()
            else:
                print("❌ Nessun actor trovato per 'transfermarkt'")
        else:
            print(f"⚠️  Errore ricerca marketplace: HTTP {response.status_code}")
    
    except Exception as e:
        print(f"❌ Errore ricerca marketplace: {e}")

def main():
    print("🔍 Controllo Apify actors per Transfermarkt...\n")
    
    # Controlla gli actor attualmente configurati
    actors_to_check = [
        "apify/transfermarkt-scraper",
        "apify/transfermarkt-players", 
        "apify/web-scraper",
        "lukaskrivka/transfermarkt-scraper"  # Esempio di actor alternativo
    ]
    
    print("📋 Controllo actor configurati:")
    for actor_id in actors_to_check:
        check_actor_exists(actor_id)
    
    print("\n" + "="*50)
    search_transfermarkt_actors()
    
    print("\n💡 Suggerimenti:")
    print("1. Se nessun actor specifico per Transfermarkt è disponibile,")
    print("   usa 'apify/web-scraper' con configurazione personalizzata")
    print("2. Considera di creare un actor personalizzato")
    print("3. Usa il fallback diretto a Transfermarkt (etl_tm_serie_a_full.py)")

if __name__ == "__main__":
    main()

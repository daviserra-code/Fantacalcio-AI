
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
debug_apify_comprehensive.py
Deep debugging for Apify integration issues
"""

import os
import json
import time
import logging
import traceback
from datetime import datetime
from apify_transfermarkt_scraper import ApifyTransfermarktScraper

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
LOG = logging.getLogger("apify_deep_debug")

def test_apify_token():
    """Test if Apify token is valid"""
    print("🔑 Testing Apify Token...")
    
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        print("❌ APIFY_API_TOKEN not found in environment")
        return False
    
    print(f"✅ Token found: {token[:10]}...{token[-4:]} (length: {len(token)})")
    
    # Test token validity with a simple API call
    import requests
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get("https://api.apify.com/v2/users/me", headers=headers, timeout=10)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"✅ Token valid - User: {user_data['data'].get('username', 'Unknown')}")
            return True
        else:
            print(f"❌ Token invalid - HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error testing token: {e}")
        return False

def test_actor_accessibility():
    """Test if the actor exists and is accessible"""
    print("\n🎭 Testing Actor Accessibility...")
    
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        return False
    
    actor_id = "yummy_pen~transfermarktscraperds"
    print(f"Testing actor: {actor_id}")
    
    import requests
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api.apify.com/v2/acts/{actor_id}"
        
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Actor API response: HTTP {response.status_code}")
        
        if response.status_code == 200:
            actor_data = response.json()
            print(f"✅ Actor found: {actor_data['data'].get('name', 'Unknown')}")
            print(f"   Description: {actor_data['data'].get('description', 'N/A')}")
            print(f"   Version: {actor_data['data'].get('taggedBuilds', {}).get('latest', {}).get('buildNumber', 'N/A')}")
            return True
        elif response.status_code == 404:
            print(f"❌ Actor not found (404)")
            print("   This could mean:")
            print("   - The actor name is incorrect")
            print("   - The actor is private and you don't have access")
            print("   - The actor has been deleted")
            return False
        else:
            print(f"❌ Unexpected response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing actor: {e}")
        return False

def test_actor_run_minimal():
    """Test running the actor with minimal input"""
    print("\n🚀 Testing Minimal Actor Run...")
    
    try:
        scraper = ApifyTransfermarktScraper()
        
        # Minimal input
        actor_input = {
            "teamUrl": "https://www.transfermarkt.it/juventus-fc/transfers/verein/506",
            "season": "2025-26"
        }
        
        print(f"Input: {json.dumps(actor_input, indent=2)}")
        print("Starting actor run...")
        
        start_time = time.time()
        result = scraper.run_actor("yummy_pen~transfermarktscraperds", actor_input, timeout_s=120)
        elapsed = time.time() - start_time
        
        print(f"✅ Actor completed in {elapsed:.1f}s")
        print(f"Status: {result.get('status')}")
        print(f"Items count: {len(result.get('items', []))}")
        
        # Analyze items structure
        items = result.get("items", [])
        if items:
            print(f"\n📊 Items Analysis:")
            print(f"Total items: {len(items)}")
            
            for i, item in enumerate(items[:3]):
                print(f"\n--- Item {i+1} ---")
                print(f"Type: {type(item)}")
                
                if isinstance(item, dict):
                    print(f"Keys: {list(item.keys())}")
                    for key, value in list(item.items())[:5]:
                        print(f"  {key}: {value} (type: {type(value)})")
                elif isinstance(item, list):
                    print(f"List length: {len(item)}")
                    if item and isinstance(item[0], dict):
                        print(f"First element keys: {list(item[0].keys())}")
                else:
                    print(f"Content: {str(item)[:100]}")
            
            # Save sample
            with open("apify_debug_sample.json", "w", encoding="utf-8") as f:
                json.dump(items[:10], f, indent=2, ensure_ascii=False, default=str)
            print(f"\n💾 Sample saved to apify_debug_sample.json")
        
        return result
        
    except Exception as e:
        print(f"❌ Error running actor: {e}")
        traceback.print_exc()
        return None

def test_normalization():
    """Test the normalization process"""
    print("\n🔄 Testing Data Normalization...")
    
    try:
        scraper = ApifyTransfermarktScraper()
        
        # Load sample data if exists
        sample_file = "apify_debug_sample.json"
        if os.path.exists(sample_file):
            with open(sample_file, "r", encoding="utf-8") as f:
                items = json.load(f)
            
            print(f"Testing normalization on {len(items)} items...")
            
            normalized_count = 0
            errors = []
            
            for i, item in enumerate(items):
                try:
                    if isinstance(item, dict):
                        transfer = scraper._normalize_transfer_data(item, "Juventus", "2025-26")
                        if transfer:
                            normalized_count += 1
                            if normalized_count <= 3:
                                print(f"✅ Normalized {normalized_count}: {transfer.get('player')} ({transfer.get('direction')})")
                        else:
                            errors.append(f"Item {i}: Normalization returned None")
                    elif isinstance(item, list):
                        for j, sub_item in enumerate(item):
                            if isinstance(sub_item, dict):
                                transfer = scraper._normalize_transfer_data(sub_item, "Juventus", "2025-26")
                                if transfer:
                                    normalized_count += 1
                                    if normalized_count <= 3:
                                        print(f"✅ Normalized {normalized_count}: {transfer.get('player')} ({transfer.get('direction')})")
                                
                except Exception as e:
                    errors.append(f"Item {i}: {str(e)}")
            
            print(f"\n📊 Normalization Results:")
            print(f"Successfully normalized: {normalized_count}/{len(items)}")
            
            if errors:
                print(f"Errors ({len(errors)}):")
                for error in errors[:5]:
                    print(f"  - {error}")
                if len(errors) > 5:
                    print(f"  ... and {len(errors) - 5} more errors")
        
        else:
            print("❌ No sample data found. Run actor test first.")
    
    except Exception as e:
        print(f"❌ Error testing normalization: {e}")
        traceback.print_exc()

def test_full_scraping():
    """Test the full scraping workflow"""
    print("\n🏗️ Testing Full Scraping Workflow...")
    
    try:
        scraper = ApifyTransfermarktScraper()
        
        print("Testing scrape_team_transfers for Juventus...")
        transfers = scraper.scrape_team_transfers("Juventus", "2025-26", arrivals_only=False)
        
        print(f"✅ Scraped {len(transfers)} transfers")
        
        if transfers:
            arrivals = [t for t in transfers if t.get("direction") == "in"]
            departures = [t for t in transfers if t.get("direction") == "out"]
            
            print(f"   Arrivals: {len(arrivals)}")
            print(f"   Departures: {len(departures)}")
            
            # Show first few transfers
            for i, transfer in enumerate(transfers[:3]):
                direction = "→" if transfer.get("direction") == "in" else "←"
                print(f"   {i+1}. {transfer.get('player')} {direction} {transfer.get('team')}")
            
            # Save full transfers
            with open("apify_debug_transfers.json", "w", encoding="utf-8") as f:
                json.dump(transfers, f, indent=2, ensure_ascii=False)
            print(f"💾 Full transfers saved to apify_debug_transfers.json")
        
        return transfers
        
    except Exception as e:
        print(f"❌ Error testing full scraping: {e}")
        traceback.print_exc()
        return []

def main():
    print("🔍 COMPREHENSIVE APIFY DEBUGGING")
    print("=" * 50)
    
    # Step 1: Test token
    if not test_apify_token():
        print("\n❌ Cannot proceed without valid Apify token")
        return
    
    # Step 2: Test actor accessibility
    if not test_actor_accessibility():
        print("\n❌ Cannot proceed without accessible actor")
        return
    
    # Step 3: Test minimal actor run
    actor_result = test_actor_run_minimal()
    if not actor_result:
        print("\n❌ Cannot proceed without successful actor run")
        return
    
    # Step 4: Test normalization
    test_normalization()
    
    # Step 5: Test full workflow
    transfers = test_full_scraping()
    
    print("\n" + "=" * 50)
    print("🎯 DEBUGGING SUMMARY:")
    print(f"✅ Token valid: Yes")
    print(f"✅ Actor accessible: Yes")
    print(f"✅ Actor runs: Yes")
    print(f"✅ Data normalization: {'Yes' if transfers else 'Check logs'}")
    print(f"📊 Final transfers count: {len(transfers) if transfers else 0}")
    
    if not transfers:
        print("\n🚨 ISSUES TO INVESTIGATE:")
        print("- Check actor output structure in apify_debug_sample.json")
        print("- Verify normalization logic matches actual data structure")
        print("- Consider modifying actor input parameters")

if __name__ == "__main__":
    main()


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
debug_apify_alternatives.py
Test alternative approaches for Apify integration
"""

import os
import json
import requests
import logging

LOG = logging.getLogger("apify_alternatives")
logging.basicConfig(level=logging.INFO)

def search_available_actors():
    """Search for available Transfermarkt actors"""
    print("🔍 Searching Available Transfermarkt Actors...")
    
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        print("❌ No Apify token")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Search in store
    try:
        response = requests.get(
            "https://api.apify.com/v2/store",
            headers=headers,
            params={"search": "transfermarkt", "limit": 20},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            actors = data.get("data", {}).get("items", [])
            
            print(f"Found {len(actors)} actors in store:")
            for actor in actors:
                print(f"  📦 {actor['id']}: {actor['title']}")
                print(f"      {actor.get('description', 'No description')[:80]}...")
                print()
        
    except Exception as e:
        print(f"❌ Error searching store: {e}")
    
    # Test some common actor IDs
    common_actors = [
        "apify/web-scraper",
        "apify/cheerio-scraper", 
        "lukaskrivka/transfermarkt-scraper",
        "drobnikj/transfermarkt-scraper"
    ]
    
    print("🧪 Testing Common Actors:")
    for actor_id in common_actors:
        try:
            response = requests.get(
                f"https://api.apify.com/v2/acts/{actor_id}",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✅ {actor_id}: Available")
            else:
                print(f"❌ {actor_id}: Not available ({response.status_code})")
                
        except Exception as e:
            print(f"❌ {actor_id}: Error - {e}")

def test_web_scraper():
    """Test using the generic web-scraper actor"""
    print("\n🕷️ Testing Generic Web Scraper...")
    
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        return
    
    # Configuration for web-scraper to scrape Transfermarkt
    scraper_config = {
        "startUrls": [
            {"url": "https://www.transfermarkt.it/juventus-fc/transfers/verein/506"}
        ],
        "pageFunction": """
        async function pageFunction(context) {
            const { page, request } = context;
            
            // Wait for the transfers table to load
            await page.waitForSelector('.responsive-table, .transfers', { timeout: 10000 });
            
            const transfers = await page.evaluate(() => {
                const rows = document.querySelectorAll('.responsive-table tbody tr, .transfers tbody tr');
                const transfers = [];
                
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 4) {
                        const player = cells[1]?.textContent?.trim();
                        const direction = row.closest('.transfers-in') ? 'in' : 'out';
                        const team = cells[2]?.textContent?.trim();
                        const fee = cells[3]?.textContent?.trim();
                        
                        if (player) {
                            transfers.push({
                                player,
                                direction,
                                team,
                                fee,
                                url: window.location.href
                            });
                        }
                    }
                });
                
                return transfers;
            });
            
            return {
                url: request.url,
                transfers: transfers,
                transferCount: transfers.length
            };
        }
        """,
        "proxyConfiguration": {"useApifyProxy": True}
    }
    
    print("Web scraper config prepared. Use this if main actor fails.")
    print(json.dumps(scraper_config, indent=2))

def create_custom_actor_template():
    """Generate a custom actor template"""
    print("\n🏗️ Creating Custom Actor Template...")
    
    actor_template = {
        "actorSpecification": 1,
        "name": "transfermarkt-serie-a-scraper",
        "title": "Transfermarkt Serie A Scraper",
        "description": "Custom scraper for Serie A transfers from Transfermarkt",
        "version": "1.0.0",
        "dockerfile": "FROM apify/actor-node:16",
        "input": {
            "title": "Input schema",
            "type": "object",
            "properties": {
                "teamUrl": {
                    "title": "Team URL", 
                    "type": "string",
                    "description": "Transfermarkt team transfers URL"
                },
                "season": {
                    "title": "Season",
                    "type": "string", 
                    "description": "Season (e.g., 2025-26)"
                },
                "extractArrivals": {
                    "title": "Extract Arrivals",
                    "type": "boolean",
                    "default": True
                },
                "extractDepartures": {
                    "title": "Extract Departures", 
                    "type": "boolean",
                    "default": True
                }
            },
            "required": ["teamUrl"]
        }
    }
    
    main_js = '''
const Apify = require('apify');

Apify.main(async () => {
    const input = await Apify.getInput();
    const { teamUrl, season = '2025-26', extractArrivals = true, extractDepartures = true } = input;
    
    const requestList = await Apify.openRequestList('start-urls', [teamUrl]);
    const requestQueue = await Apify.openRequestQueue();
    const proxyConfiguration = await Apify.createProxyConfiguration({
        groups: ['RESIDENTIAL']
    });
    
    const crawler = new Apify.PuppeteerCrawler({
        requestList,
        requestQueue,
        proxyConfiguration,
        handlePageFunction: async ({ page, request }) => {
            console.log(`Processing: ${request.url}`);
            
            // Wait for transfers sections
            await page.waitForSelector('.large-8.columns', { timeout: 15000 });
            
            const transfers = await page.evaluate((season, extractArrivals, extractDepartures) => {
                const results = [];
                
                // Find arrivals section
                if (extractArrivals) {
                    const arrivalsSection = document.querySelector('.box:has(.table-header:contains("Arrivi"))');
                    if (arrivalsSection) {
                        const rows = arrivalsSection.querySelectorAll('tbody tr');
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            if (cells.length >= 5) {
                                const player = cells[0]?.textContent?.trim();
                                const position = cells[1]?.textContent?.trim(); 
                                const fromTeam = cells[2]?.textContent?.trim();
                                const fee = cells[3]?.textContent?.trim();
                                
                                if (player && player !== '-') {
                                    results.push({
                                        player,
                                        position,
                                        direction: 'in',
                                        from_team: fromTeam,
                                        to_team: '', // Will be filled from URL
                                        fee,
                                        season
                                    });
                                }
                            }
                        });
                    }
                }
                
                // Find departures section  
                if (extractDepartures) {
                    const departuresSection = document.querySelector('.box:has(.table-header:contains("Partenze"))');
                    if (departuresSection) {
                        const rows = departuresSection.querySelectorAll('tbody tr');
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            if (cells.length >= 5) {
                                const player = cells[0]?.textContent?.trim();
                                const position = cells[1]?.textContent?.trim();
                                const toTeam = cells[2]?.textContent?.trim();
                                const fee = cells[3]?.textContent?.trim();
                                
                                if (player && player !== '-') {
                                    results.push({
                                        player,
                                        position, 
                                        direction: 'out',
                                        from_team: '', // Will be filled from URL
                                        to_team: toTeam,
                                        fee,
                                        season
                                    });
                                }
                            }
                        });
                    }
                }
                
                return results;
            }, season, extractArrivals, extractDepartures);
            
            // Extract team name from URL
            const teamName = request.url.match(/\\/([^/]+)\\/transfers/)?.[1] || '';
            
            // Add team info to transfers
            transfers.forEach(transfer => {
                if (transfer.direction === 'in') {
                    transfer.to_team = teamName;
                } else {
                    transfer.from_team = teamName;
                }
            });
            
            console.log(`Found ${transfers.length} transfers`);
            
            // Save to dataset
            await Apify.pushData(transfers);
        },
        maxRequestsPerCrawl: 10,
        maxConcurrency: 1
    });
    
    await crawler.run();
    console.log('Crawler finished.');
});
'''
    
    print("Custom actor template generated!")
    print("You can create this actor in Apify Console if needed.")
    
    with open("custom_actor_template.json", "w") as f:
        json.dump(actor_template, f, indent=2)
    
    with open("custom_actor_main.js", "w") as f:
        f.write(main_js)
    
    print("Files saved: custom_actor_template.json, custom_actor_main.js")

def main():
    print("🔧 APIFY ALTERNATIVES DEBUGGING")
    print("=" * 50)
    
    search_available_actors()
    test_web_scraper() 
    create_custom_actor_template()
    
    print("\n💡 RECOMMENDATIONS:")
    print("1. If main actor fails, try apify/web-scraper with custom config")
    print("2. Create custom actor using provided template")
    print("3. Fallback to direct scraping (etl_tm_serie_a_full.py)")

if __name__ == "__main__":
    main()

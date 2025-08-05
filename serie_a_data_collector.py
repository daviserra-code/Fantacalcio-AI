
import requests
import json
import time
from bs4 import BeautifulSoup
from knowledge_manager import KnowledgeManager
from datetime import datetime

class SerieADataCollector:
    def __init__(self):
        self.km = KnowledgeManager()
        self.current_season = "2025-26"
        
    def collect_transfermarkt_data(self, team_urls):
        """Collect data from Transfermarkt for Serie A teams"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        players_data = []
        
        for team_name, url in team_urls.items():
            try:
                print(f"🔄 Collecting data for {team_name}...")
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract player information (simplified example)
                players = soup.find_all('tr', class_='odd') + soup.find_all('tr', class_='even')
                
                for player in players:
                    try:
                        name_elem = player.find('a', {'class': 'spielprofil_tooltip'})
                        if name_elem:
                            player_data = {
                                'name': name_elem.text.strip(),
                                'team': team_name,
                                'season': self.current_season,
                                'source': 'transfermarkt',
                                'updated_at': datetime.now().isoformat()
                            }
                            players_data.append(player_data)
                    except Exception as e:
                        continue
                        
                time.sleep(2)  # Rate limiting
                
            except Exception as e:
                print(f"❌ Error collecting data for {team_name}: {e}")
                
        return players_data
    
    def collect_wikipedia_data(self, serie_a_teams):
        """Collect Serie A data from Wikipedia"""
        players_data = []
        
        for team in serie_a_teams:
            try:
                # Wikipedia API for Serie A squad information
                wiki_url = f"https://it.wikipedia.org/api/rest_v1/page/summary/{team}_calcio"
                response = requests.get(wiki_url)
                
                if response.status_code == 200:
                    data = response.json()
                    # Process Wikipedia data for team information
                    team_info = {
                        'team': team,
                        'description': data.get('extract', ''),
                        'source': 'wikipedia',
                        'updated_at': datetime.now().isoformat()
                    }
                    players_data.append(team_info)
                    
                time.sleep(1)  # Rate limiting
                
            except Exception as e:
                print(f"❌ Error collecting Wikipedia data for {team}: {e}")
                
        return players_data
    
    def update_knowledge_base(self):
        """Update knowledge base with fresh Serie A data"""
        
        # Serie A teams for 2025-26
        serie_a_teams = [
            "Inter", "Milan", "Juventus", "Napoli", "Roma", "Lazio", 
            "Atalanta", "Fiorentina", "Bologna", "Torino", "Udinese",
            "Sassuolo", "Empoli", "Verona", "Cagliari", "Lecce",
            "Monza", "Frosinone", "Genoa", "Salernitana"
        ]
        
        # Transfermarkt URLs (example structure)
        transfermarkt_urls = {
            "Inter": "https://www.transfermarkt.it/fc-internazionale-milano/startseite/verein/46",
            "Milan": "https://www.transfermarkt.it/ac-mailand/startseite/verein/5",
            "Juventus": "https://www.transfermarkt.it/juventus-turin/startseite/verein/506",
            # Add more teams as needed
        }
        
        print("🔄 Starting Serie A data collection...")
        
        # Collect data
        transfermarkt_data = self.collect_transfermarkt_data(transfermarkt_urls)
        wikipedia_data = self.collect_wikipedia_data(serie_a_teams)
        
        # Add to knowledge base
        for data in transfermarkt_data + wikipedia_data:
            text = f"{data.get('name', data.get('team', ''))} - {data.get('description', '')}"
            metadata = {
                'type': 'real_time_data',
                'source': data['source'],
                'updated_at': data['updated_at'],
                'season': self.current_season
            }
            
            self.km.add_knowledge(text, metadata)
        
        print(f"✅ Added {len(transfermarkt_data + wikipedia_data)} entries to knowledge base")
        
        # Export updated data
        self.export_updated_data()
    
    def export_updated_data(self):
        """Export updated data to JSONL"""
        # This would export the updated knowledge base
        print("📄 Exporting updated Serie A data...")
        # Implementation would depend on ChromaDB export capabilities

if __name__ == "__main__":
    collector = SerieADataCollector()
    collector.update_knowledge_base()

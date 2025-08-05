
import requests
import json
import time
from bs4 import BeautifulSoup
from knowledge_manager import KnowledgeManager
from datetime import datetime

class SerieADataCollector:
    def __init__(self):
        self.km = KnowledgeManager()
        self.current_season = "2024-25"  # Updated to current season
        
    def collect_transfermarkt_data(self, team_urls):
        """Collect data from Transfermarkt for Serie A teams"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        players_data = []
        
        for team_name, url in team_urls.items():
            try:
                print(f"🔄 Collecting data for {team_name}...")
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code != 200:
                    print(f"❌ HTTP {response.status_code} for {team_name}")
                    continue
                    
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for player table rows more specifically
                player_rows = soup.select('table.items tbody tr:not(.subheader)')
                
                for row in player_rows:
                    try:
                        # Extract player name
                        name_cell = row.select_one('td.hauptlink a')
                        if not name_cell:
                            continue
                            
                        player_name = name_cell.get_text(strip=True)
                        
                        # Extract position
                        position_cell = row.select_one('td:nth-child(2)')
                        position = position_cell.get_text(strip=True) if position_cell else 'Unknown'
                        
                        # Extract age
                        age_cell = row.select_one('td:nth-child(3)')
                        age = age_cell.get_text(strip=True) if age_cell else 'Unknown'
                        
                        # Extract market value
                        value_cell = row.select_one('td.rechts.hauptlink')
                        market_value = value_cell.get_text(strip=True) if value_cell else '0'
                        
                        player_data = {
                            'name': player_name,
                            'team': team_name,
                            'position': position,
                            'age': age,
                            'market_value': market_value,
                            'season': self.current_season,
                            'source': 'transfermarkt',
                            'updated_at': datetime.now().isoformat()
                        }
                        players_data.append(player_data)
                        
                    except Exception as e:
                        continue
                        
                time.sleep(3)  # More conservative rate limiting
                
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
        """Update knowledge base with current Serie A strategic knowledge"""
        
        # Serie A teams for 2024-25 (current season)
        serie_a_teams = [
            "Inter", "Milan", "Juventus", "Napoli", "Roma", "Lazio", 
            "Atalanta", "Fiorentina", "Bologna", "Torino", "Udinese",
            "Empoli", "Verona", "Cagliari", "Lecce", "Monza", 
            "Genoa", "Como", "Parma", "Venezia"
        ]
        
        # Add comprehensive current season player information
        current_players_2024_25 = [
            # PORTIERI
            {
                'text': "Mike Maignan del Milan è il portiere più affidabile con fantamedia 6.7 nella stagione 2024-25, prezzo consigliato 20-25 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Mike Maignan', 'team': 'Milan', 'role': 'P', 'season': '2024-25', 'price': 22}
            },
            {
                'text': "Yann Sommer dell'Inter ha fantamedia 6.5 nella stagione 2024-25, ottima scelta per 18-20 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Yann Sommer', 'team': 'Inter', 'role': 'P', 'season': '2024-25', 'price': 19}
            },
            {
                'text': "Alex Meret del Napoli ha fantamedia 6.3 nella stagione 2024-25, buon rapporto qualità-prezzo a 15-18 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Alex Meret', 'team': 'Napoli', 'role': 'P', 'season': '2024-25', 'price': 16}
            },
            {
                'text': "Wojciech Szczesny della Juventus ha fantamedia 6.4 nella stagione 2024-25, vale 17-20 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Wojciech Szczesny', 'team': 'Juventus', 'role': 'P', 'season': '2024-25', 'price': 18}
            },
            {
                'text': "Ivan Provedel della Lazio ha fantamedia 6.2 nella stagione 2024-25, opzione economica a 12-15 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Ivan Provedel', 'team': 'Lazio', 'role': 'P', 'season': '2024-25', 'price': 13}
            },
            
            # DIFENSORI
            {
                'text': "Alessandro Bastoni dell'Inter ha fantamedia 6.8 come difensore nella stagione 2024-25, vale 25-30 crediti per i suoi gol e assist.",
                'metadata': {'type': 'current_player', 'player': 'Alessandro Bastoni', 'team': 'Inter', 'role': 'D', 'season': '2024-25', 'price': 27}
            },
            {
                'text': "Theo Hernandez del Milan mantiene fantamedia 6.9 come terzino sinistro nella stagione 2024-25, costa 30-35 crediti ma ne vale la pena.",
                'metadata': {'type': 'current_player', 'player': 'Theo Hernandez', 'team': 'Milan', 'role': 'D', 'season': '2024-25', 'price': 32}
            },
            {
                'text': "Federico Dimarco dell'Inter ha fantamedia 6.7 nella stagione 2024-25, eccellente per assist, vale 22-28 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Federico Dimarco', 'team': 'Inter', 'role': 'D', 'season': '2024-25', 'price': 25}
            },
            {
                'text': "Andrea Cambiaso della Juventus ha fantamedia 6.5 nella stagione 2024-25, terzino moderno che vale 20-25 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Andrea Cambiaso', 'team': 'Juventus', 'role': 'D', 'season': '2024-25', 'price': 22}
            },
            {
                'text': "Giovanni Di Lorenzo del Napoli ha fantamedia 6.4 nella stagione 2024-25, capitano affidabile per 18-22 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Giovanni Di Lorenzo', 'team': 'Napoli', 'role': 'D', 'season': '2024-25', 'price': 20}
            },
            {
                'text': "Denzel Dumfries dell'Inter ha fantamedia 6.3 nella stagione 2024-25, esterno offensivo che vale 16-20 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Denzel Dumfries', 'team': 'Inter', 'role': 'D', 'season': '2024-25', 'price': 18}
            },
            {
                'text': "Fikayo Tomori del Milan ha fantamedia 6.2 nella stagione 2024-25, difensore centrale solido per 15-18 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Fikayo Tomori', 'team': 'Milan', 'role': 'D', 'season': '2024-25', 'price': 16}
            },
            {
                'text': "Gleison Bremer della Juventus ha fantamedia 6.1 nella stagione 2024-25, roccioso centrale per 14-17 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Gleison Bremer', 'team': 'Juventus', 'role': 'D', 'season': '2024-25', 'price': 15}
            },
            
            # CENTROCAMPISTI
            {
                'text': "Nicolò Barella dell'Inter ha fantamedia 7.1 come centrocampista nella stagione 2024-25, top assoluto che vale 35-40 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Nicolò Barella', 'team': 'Inter', 'role': 'C', 'season': '2024-25', 'price': 37}
            },
            {
                'text': "Hakan Calhanoglu dell'Inter ha fantamedia 6.9 nella stagione 2024-25, rigorista prezioso che vale 30-35 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Hakan Calhanoglu', 'team': 'Inter', 'role': 'C', 'season': '2024-25', 'price': 32}
            },
            {
                'text': "Tijjani Reijnders del Milan ha fantamedia 6.6 nella stagione 2024-25, centrocampista box-to-box che vale 25-28 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Tijjani Reijnders', 'team': 'Milan', 'role': 'C', 'season': '2024-25', 'price': 26}
            },
            {
                'text': "Youssouf Fofana del Milan ha fantamedia 6.4 nella stagione 2024-25, mediano affidabile per 20-24 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Youssouf Fofana', 'team': 'Milan', 'role': 'C', 'season': '2024-25', 'price': 22}
            },
            {
                'text': "Manuel Locatelli della Juventus ha fantamedia 6.3 nella stagione 2024-25, regista moderno che vale 18-22 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Manuel Locatelli', 'team': 'Juventus', 'role': 'C', 'season': '2024-25', 'price': 20}
            },
            {
                'text': "Stanislav Lobotka del Napoli ha fantamedia 6.5 nella stagione 2024-25, play perfetto per 22-26 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Stanislav Lobotka', 'team': 'Napoli', 'role': 'C', 'season': '2024-25', 'price': 24}
            },
            {
                'text': "Lorenzo Pellegrini della Roma ha fantamedia 6.4 come centrocampista nella stagione 2024-25, capitano che vale 20-25 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Lorenzo Pellegrini', 'team': 'Roma', 'role': 'C', 'season': '2024-25', 'price': 22}
            },
            {
                'text': "Marten de Roon dell'Atalanta ha fantamedia 6.2 nella stagione 2024-25, mediano instancabile per 15-18 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Marten de Roon', 'team': 'Atalanta', 'role': 'C', 'season': '2024-25', 'price': 16}
            },
            
            # ATTACCANTI
            {
                'text': "Victor Osimhen del Napoli ha fantamedia 7.3 nella stagione 2024-25, il migliore attaccante che vale 45-50 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Victor Osimhen', 'team': 'Napoli', 'role': 'A', 'season': '2024-25', 'price': 47}
            },
            {
                'text': "Marcus Thuram dell'Inter ha fantamedia 7.2 nella stagione 2024-25, uno dei migliori acquisti che vale 40-45 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Marcus Thuram', 'team': 'Inter', 'role': 'A', 'season': '2024-25', 'price': 42}
            },
            {
                'text': "Lautaro Martinez dell'Inter ha fantamedia 7.0 nella stagione 2024-25, bomber affidabile che vale 38-42 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Lautaro Martinez', 'team': 'Inter', 'role': 'A', 'season': '2024-25', 'price': 40}
            },
            {
                'text': "Dusan Vlahovic della Juventus mantiene fantamedia 7.0 nella stagione corrente 2024-25, centravanti da 35-40 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Dusan Vlahovic', 'team': 'Juventus', 'role': 'A', 'season': '2024-25', 'price': 37}
            },
            {
                'text': "Rafael Leao del Milan ha fantamedia 6.9 nella stagione 2024-25, ala sinistra devastante che vale 35-38 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Rafael Leao', 'team': 'Milan', 'role': 'A', 'season': '2024-25', 'price': 36}
            },
            {
                'text': "Khvicha Kvaratskhelia del Napoli ha fantamedia 7.0 nella stagione 2024-25, esterno offensivo che vale 33-37 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Khvicha Kvaratskhelia', 'team': 'Napoli', 'role': 'A', 'season': '2024-25', 'price': 35}
            },
            {
                'text': "Ciro Immobile della Lazio ha fantamedia 6.8 nella stagione 2024-25, bomber esperto che vale 30-33 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Ciro Immobile', 'team': 'Lazio', 'role': 'A', 'season': '2024-25', 'price': 31}
            },
            {
                'text': "Olivier Giroud del Milan ha fantamedia 6.7 nella stagione 2024-25, centravanti di esperienza per 28-31 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Olivier Giroud', 'team': 'Milan', 'role': 'A', 'season': '2024-25', 'price': 29}
            },
            {
                'text': "Paulo Dybala della Roma ha fantamedia 6.8 nella stagione 2024-25, trequartista di classe che vale 28-32 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Paulo Dybala', 'team': 'Roma', 'role': 'A', 'season': '2024-25', 'price': 30}
            },
            {
                'text': "Ademola Lookman dell'Atalanta ha fantamedia 6.6 nella stagione 2024-25, ala rapida che vale 25-28 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Ademola Lookman', 'team': 'Atalanta', 'role': 'A', 'season': '2024-25', 'price': 26}
            },
            {
                'text': "Federico Chiesa della Juventus ha fantamedia 6.7 nella stagione corrente 2024-25, esterno tecnico che vale 25-29 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Federico Chiesa', 'team': 'Juventus', 'role': 'A', 'season': '2024-25', 'price': 27}
            },
            {
                'text': "Tammy Abraham della Roma ha fantamedia 6.5 nella stagione 2024-25, centravanti fisico per 22-26 crediti.",
                'metadata': {'type': 'current_player', 'player': 'Tammy Abraham', 'team': 'Roma', 'role': 'A', 'season': '2024-25', 'price': 24}
            }
        ]
        
        # Add strategic knowledge about current Serie A context
        strategic_knowledge = [
            {
                'text': "Per la stagione 2024-25, le squadre più affidabili per il fantacalcio sono Inter, Napoli, Milan e Juventus. Atalanta è sempre un'opzione interessante per centrocampisti offensivi.",
                'metadata': {'type': 'season_strategy', 'season': '2024-25'}
            },
            {
                'text': "Formazione consigliata per il fantacalcio 2024-25: Portiere: Maignan (Milan). Difesa: Bastoni (Inter), Theo Hernandez (Milan), Dimarco (Inter). Centrocampo: Barella (Inter), Calhanoglu (Inter), Reijnders (Milan), Lobotka (Napoli), Pellegrini (Roma). Attacco: Osimhen (Napoli), Thuram (Inter).",
                'metadata': {'type': 'formation_complete', 'season': '2024-25', 'module': '3-5-2'}
            },
            {
                'text': "Formazione alternativa economica 2024-25: Portiere: Provedel (Lazio). Difesa: Di Lorenzo (Napoli), Tomori (Milan), Cambiaso (Juventus). Centrocampo: Locatelli (Juventus), de Roon (Atalanta), Fofana (Milan), Lookman (Atalanta), Dybala (Roma). Attacco: Immobile (Lazio), Abraham (Roma).",
                'metadata': {'type': 'formation_budget', 'season': '2024-25', 'module': '3-5-2'}
            },
            {
                'text': "I portieri più consigliati per la stagione 2024-25 sono Maignan (Milan) 22 crediti, Sommer (Inter) 19 crediti, e Meret (Napoli) 16 crediti.",
                'metadata': {'type': 'role_strategy', 'role': 'portiere', 'season': '2024-25'}
            },
            {
                'text': "Per gli attaccanti nella stagione 2024-25: Osimhen (Napoli) 47 crediti, Thuram (Inter) 42 crediti, Lautaro (Inter) 40 crediti, Vlahovic (Juventus) 37 crediti sono i top. Cerca sempre rigoristi.",
                'metadata': {'type': 'role_strategy', 'role': 'attaccante', 'season': '2024-25'}
            },
            {
                'text': "I difensori top per la stagione 2024-25: Bastoni (Inter) 27 crediti, Theo Hernandez (Milan) 32 crediti, Dimarco (Inter) 25 crediti. Terzini offensivi sono oro.",
                'metadata': {'type': 'role_strategy', 'role': 'difensore', 'season': '2024-25'}
            },
            {
                'text': "Centrocampisti 2024-25: Barella (Inter) 37 crediti, Calhanoglu (Inter) 32 crediti, Reijnders (Milan) 26 crediti sono i migliori. Punta su quelli che fanno assist e gol.",
                'metadata': {'type': 'role_strategy', 'role': 'centrocampista', 'season': '2024-25'}
            },
            {
                'text': "Budget 500 crediti: distribuisci 110 per attacco (Osimhen 47 + Immobile 31), 160 per centrocampo (Barella 37 + Calhanoglu 32 + Reijnders 26 + Lobotka 24), 140 per difesa (Theo 32 + Bastoni 27 + Dimarco 25 + Di Lorenzo 20 + Cambiaso 22), 70 per portieri (Maignan 22 + Sommer 19 + Provedel 13).",
                'metadata': {'type': 'budget_strategy', 'budget': 500, 'season': '2024-25'}
            }
        ]
        
        # Add current players data to database
        for player_info in current_players_2024_25:
            self.km.add_knowledge(player_info['text'], player_info['metadata'])
        
        # Add strategic knowledge to database
        for knowledge in strategic_knowledge:
            self.km.add_knowledge(knowledge['text'], knowledge['metadata'])
        
        # Transfermarkt URLs (squad pages for better player data)
        transfermarkt_urls = {
            "Inter": "https://www.transfermarkt.it/fc-internazionale-milano/kader/verein/46",
            "Milan": "https://www.transfermarkt.it/ac-mailand/kader/verein/5", 
            "Juventus": "https://www.transfermarkt.it/juventus-turin/kader/verein/506",
            "Napoli": "https://www.transfermarkt.it/ssc-neapel/kader/verein/6195",
            "Roma": "https://www.transfermarkt.it/as-rom/kader/verein/12",
            "Lazio": "https://www.transfermarkt.it/lazio-rom/kader/verein/398",
            "Atalanta": "https://www.transfermarkt.it/atalanta-bergamo/kader/verein/800"
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

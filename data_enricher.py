
import json
from fantacalcio_data import SAMPLE_PLAYERS, League, AuctionHelper
from knowledge_manager import KnowledgeManager

def generate_player_knowledge():
    """Generate knowledge entries for all sample players"""
    knowledge_entries = []
    
    for player in SAMPLE_PLAYERS:
        # Basic player info
        basic_info = f"{player.name} è {'un portiere' if player.role == 'P' else 'un difensore' if player.role == 'D' else 'un centrocampista' if player.role == 'C' else 'un attaccante'} {f'del {player.team}' if player.team else ''} con fantamedia {player.fantamedia} e prezzo consigliato {player.price}. Ha giocato {player.appearances} partite nella stagione."
        
        knowledge_entries.append({
            "text": basic_info,
            "metadata": {
                "type": "player_info",
                "role": player.role,
                "team": player.team,
                "player": player.name,
                "price": player.price,
                "fantamedia": player.fantamedia
            },
            "id": f"{player.name.lower().replace(' ', '_')}_basic"
        })
        
        # Price analysis
        if player.price > 30:
            price_analysis = f"{player.name} costa {player.price} crediti, è un investimento importante. Con fantamedia {player.fantamedia}, {'si ripaga' if player.fantamedia > 6.5 else 'potrebbe essere rischioso'}."
            knowledge_entries.append({
                "text": price_analysis,
                "metadata": {
                    "type": "price_analysis",
                    "role": player.role,
                    "player": player.name,
                    "price_tier": "premium"
                },
                "id": f"{player.name.lower().replace(' ', '_')}_price"
            })
        
        # Role-specific advice
        if player.role == "A" and player.fantamedia > 6.5:
            advice = f"{player.name} è un attaccante affidabile per il fantacalcio. Con fantamedia {player.fantamedia}, è una scelta sicura per l'attacco."
            knowledge_entries.append({
                "text": advice,
                "metadata": {
                    "type": "role_recommendation",
                    "role": "A",
                    "player": player.name,
                    "tier": "top"
                },
                "id": f"{player.name.lower().replace(' ', '_')}_recommendation"
            })
    
    return knowledge_entries

def generate_strategy_knowledge():
    """Generate strategic knowledge for different league types"""
    strategies = []
    
    # Budget strategies
    budgets = [300, 500, 750, 1000]
    for budget in budgets:
        strategy = f"Con budget {budget}, consiglia di distribuire: {int(budget*0.22)}% per l'attacco ({int(budget*0.22)} crediti), {int(budget*0.32)}% per il centrocampo ({int(budget*0.32)} crediti), {int(budget*0.28)}% per la difesa ({int(budget*0.28)} crediti), {int(budget*0.18)}% per i portieri ({int(budget*0.18)} crediti)."
        
        strategies.append({
            "text": strategy,
            "metadata": {
                "type": "budget_strategy",
                "budget": budget,
                "category": "distribution"
            },
            "id": f"budget_strategy_{budget}"
        })
    
    # League type strategies
    league_strategies = {
        "Classic": "Nel Classic, punta su giocatori con fantamedia alta e bonus frequenti. Evita scommesse rischiose.",
        "Mantra": "Nel Mantra, gli assist valgono di più. Priorizza centrocampisti creativi e esterni offensivi.",
        "Draft": "Nel Draft non c'è budget. Prendi prima i migliori giocatori disponibili, indipendentemente dal ruolo.",
        "Superscudetto": "Nel Superscudetto, i premi extra giustificano investimenti su top player. Meglio pochi fenomeni che tanti buoni."
    }
    
    for league_type, strategy in league_strategies.items():
        strategies.append({
            "text": strategy,
            "metadata": {
                "type": "league_strategy",
                "league_type": league_type
            },
            "id": f"strategy_{league_type.lower()}"
        })
    
    return strategies

def enrich_knowledge_base():
    """Enrich the knowledge base with generated data"""
    km = KnowledgeManager()
    
    # Generate and add player knowledge
    player_knowledge = generate_player_knowledge()
    for entry in player_knowledge:
        km.add_knowledge(entry["text"], entry["metadata"], entry["id"])
    
    # Generate and add strategy knowledge
    strategy_knowledge = generate_strategy_knowledge()
    for entry in strategy_knowledge:
        km.add_knowledge(entry["text"], entry["metadata"], entry["id"])
    
    print(f"✅ Added {len(player_knowledge)} player entries and {len(strategy_knowledge)} strategy entries to knowledge base")

def export_to_jsonl(filename="extended_training_data.jsonl"):
    """Export all generated knowledge to JSONL for fine-tuning"""
    all_entries = []
    
    # Get player and strategy knowledge
    all_entries.extend(generate_player_knowledge())
    all_entries.extend(generate_strategy_knowledge())
    
    # Write to JSONL
    with open(filename, 'w', encoding='utf-8') as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    print(f"✅ Exported {len(all_entries)} entries to {filename}")

if __name__ == "__main__":
    print("🔄 Enriching knowledge base...")
    enrich_knowledge_base()
    
    print("📄 Exporting to JSONL...")
    export_to_jsonl()
    
    print("✅ Knowledge base enrichment completed!")

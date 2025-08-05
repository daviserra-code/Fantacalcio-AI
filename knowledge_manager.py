
import json
from rag_system import FantacalcioRAGSystem
from typing import Dict, List

class KnowledgeManager:
    def __init__(self):
        self.rag_system = FantacalcioRAGSystem()
    
    def create_training_data_from_conversations(self, conversations: List[Dict]) -> str:
        """Convert conversation data to JSONL format"""
        jsonl_lines = []
        
        for conv in conversations:
            if 'question' in conv and 'answer' in conv:
                jsonl_data = {
                    "text": conv['question'],
                    "answer": conv['answer'],
                    "type": "conversation",
                    "category": conv.get('category', 'general')
                }
                
                # Add league type if available
                if 'league_type' in conv:
                    jsonl_data['league_type'] = conv['league_type']
                
                # Add player/team info if available
                if 'player' in conv:
                    jsonl_data['player'] = conv['player']
                if 'team' in conv:
                    jsonl_data['team'] = conv['team']
                
                jsonl_lines.append(json.dumps(jsonl_data, ensure_ascii=False))
        
        return '\n'.join(jsonl_lines)
    
    def add_player_statistics(self, player_data: Dict):
        """Add player statistics to knowledge base"""
        text = f"{player_data['name']} ({player_data['team']}) - Ruolo: {player_data['role']}, "
        text += f"Fantamedia: {player_data.get('fantamedia', 'N/A')}, "
        text += f"Presenze: {player_data.get('appearances', 'N/A')}"
        
        metadata = {
            "type": "player_stats",
            "player": player_data['name'],
            "team": player_data['team'],
            "role": player_data['role']
        }
        
        self.rag_system.add_knowledge(text, metadata)
    
    def add_strategy_tip(self, tip: str, league_type: str = None, category: str = "general"):
        """Add strategy tip to knowledge base"""
        metadata = {
            "type": "strategy",
            "category": category
        }
        
        if league_type:
            metadata["league_type"] = league_type
        
        self.rag_system.add_knowledge(tip, metadata)
    
    def export_knowledge_to_jsonl(self, output_file: str):
        """Export current knowledge base to JSONL file"""
        # This would require accessing ChromaDB's internal data
        # Implementation depends on specific needs
        pass
    
    def retrain_from_jsonl(self, jsonl_file: str):
        """Clear current knowledge and retrain from JSONL"""
        self.rag_system.clear_collection()
        self.rag_system.load_jsonl_data(jsonl_file)
        print(f"Retrained knowledge base from {jsonl_file}")

# Example usage functions
def create_sample_conversation_data():
    """Create sample conversation data for training"""
    conversations = [
        {
            "question": "Quanto dovrei spendere per Vlahovic?",
            "answer": "Per Vlahovic in una lega Classic da 8, considera 35-40 fantamilioni. È un attaccante affidabile con buona continuità di rendimento.",
            "category": "player_valuation",
            "league_type": "Classic",
            "player": "Vlahovic"
        },
        {
            "question": "Come funziona il bonus assist nel Mantra?",
            "answer": "Nel Mantra ogni assist vale +1 punto. Questo rende molto preziosi centrocampisti creativi come Pellegrini, Zaniolo e le ali offensive.",
            "category": "rules",
            "league_type": "Mantra"
        }
    ]
    
    km = KnowledgeManager()
    jsonl_data = km.create_training_data_from_conversations(conversations)
    
    with open('training_conversations.jsonl', 'w', encoding='utf-8') as f:
        f.write(jsonl_data)
    
    return jsonl_data

if __name__ == "__main__":
    # Example: create and load training data
    create_sample_conversation_data()
    
    # Load the training data
    km = KnowledgeManager()
    km.retrain_from_jsonl('training_conversations.jsonl')

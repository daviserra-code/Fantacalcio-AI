import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class CorrectionsManager:
    """Simple corrections manager using the KnowledgeManager as backend"""

    def __init__(self, knowledge_manager=None):
        self.knowledge_manager = knowledge_manager

    def add_correction(self, correction_type: str, incorrect_info: str,
                      correct_info: str, context: str = None):
        """Add a new correction to the system"""
        if not self.knowledge_manager:
            return "corrections_disabled"

        try:
            correction_text = f"CORREZIONE: Sostituisci '{incorrect_info}' con '{correct_info}'"
            correction_id = self.knowledge_manager.add_knowledge(
                correction_text,
                {
                    "type": "correction",
                    "correction_type": correction_type,
                    "wrong": incorrect_info,
                    "correct": correct_info,
                    "context": context,
                    "created_at": datetime.now().isoformat()
                }
            )
            return correction_id
        except Exception as e:
            logger.error(f"Failed to add correction: {e}")
            return None

    def add_player_correction(self, player_name: str, field_name: str,
                            old_value: str, new_value: str, reason: str = None):
        """Add a player-specific correction"""
        return self.add_correction(
            "player_data",
            f"{player_name} {field_name}: {old_value}",
            f"{player_name} {field_name}: {new_value}",
            reason
        )

    def search_knowledge(self, query: str, n_results: int = 10):
        """Search corrections using knowledge manager"""
        if not self.knowledge_manager:
            return []
        
        try:
            return self.knowledge_manager.search_knowledge(query, n_results)
        except Exception as e:
            logger.error(f"Failed to search corrections: {e}")
            return []

    def get_corrections(self, limit: int = 50) -> List[Dict]:
        """Get all corrections"""
        if not self.knowledge_manager:
            return []

        try:
            results = self.knowledge_manager.search_knowledge("CORREZIONE", n_results=limit)
            return [r for r in results if r.get('metadata', {}).get('type') == 'correction']
        except Exception as e:
            logger.error(f"Failed to get corrections: {e}")
            return []
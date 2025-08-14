
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

class CorrectionsManager:
    """Enhanced corrections manager with better retrieval and application"""

    def __init__(self, knowledge_manager=None):
        self.knowledge_manager = knowledge_manager
        self._correction_cache = {}  # Cache for faster lookups

    def add_correction(self, correction_type: str, incorrect_info: str,
                      correct_info: str, context: str = None):
        """Add a new correction to the system"""
        if not self.knowledge_manager:
            return "corrections_disabled"

        try:
            correction_text = f"CORREZIONE: Sostituisci '{incorrect_info}' con '{correct_info}'"
            metadata = {
                "type": "correction",
                "correction_type": correction_type,
                "wrong": incorrect_info,
                "correct": correct_info,
                "context": context or "",
                "created_at": datetime.now().isoformat(),
                "priority": "high"
            }

            # Add to Chroma collection directly
            import uuid
            doc_id = str(uuid.uuid4())
            self.knowledge_manager.collection.add(
                documents=[correction_text],
                metadatas=[metadata],
                ids=[doc_id]
            )

            # Update cache
            self._update_correction_cache(incorrect_info, correct_info)

            logger.info(f"Added correction: {correction_text}")
            return doc_id
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

    def _update_correction_cache(self, wrong_info: str, correct_info: str):
        """Update internal cache for fast correction lookup"""
        # Extract player names and teams for caching
        players = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', wrong_info + " " + correct_info)
        for player in players:
            if len(player) > 3:  # Avoid short words
                self._correction_cache[player.lower()] = {
                    "wrong": wrong_info,
                    "correct": correct_info,
                    "timestamp": datetime.now().isoformat()
                }

    def get_relevant_corrections(self, query: str, limit: int = 10) -> List[Dict]:
        """Get corrections relevant to the query"""
        if not self.knowledge_manager:
            return []

        try:
            # Search for corrections related to the query
            where_filter = {
                "$and": [
                    {"type": {"$eq": "correction"}},
                    {"priority": {"$eq": "high"}}
                ]
            }

            results = self.knowledge_manager.search_knowledge(
                text=query,
                where=where_filter,
                n_results=limit,
                include=["documents", "metadatas"]
            )

            corrections = []
            if results and "metadatas" in results:
                metadatas = results["metadatas"]
                documents = results.get("documents", [])

                # Handle both single query and multiple query results
                if isinstance(metadatas[0], list):
                    metadatas = metadatas[0]
                    documents = documents[0] if documents else []

                for i, metadata in enumerate(metadatas):
                    if metadata and metadata.get("type") == "correction":
                        correction = {
                            "wrong": metadata.get("wrong", ""),
                            "correct": metadata.get("correct", ""),
                            "context": metadata.get("context", ""),
                            "created_at": metadata.get("created_at", ""),
                            "document": documents[i] if i < len(documents) else ""
                        }
                        corrections.append(correction)

            return corrections

        except Exception as e:
            logger.error(f"Failed to get relevant corrections: {e}")
            return []

    def apply_corrections_to_text(self, text: str) -> Tuple[str, List[str]]:
        """Apply stored corrections to text"""
        if not text:
            return text, []

        corrections = self.get_corrections()
        if not corrections:
            return text, []

        corrected_text = text
        applied_corrections = []

        for correction in corrections:
            try:
                wrong = correction.get("wrong", "")
                correct = correction.get("correct", "")
                context = correction.get("context", "")

                if not (wrong and correct):
                    continue

                # Extract player name and team info from correction
                correct_match = re.search(r'(\w+(?:\s+\w+)*)\s+team:\s*(.+?)\s*->\s*(.+)', correct)

                if correct_match:
                    player_name = correct_match.group(1).strip()
                    old_team = correct_match.group(2).strip()
                    new_team = correct_match.group(3).strip()

                    # Check if this player appears in the text
                    if player_name.lower() in corrected_text.lower():
                        
                        # Pattern 1: "**Player Name** (Team)" format
                        player_pattern = re.escape(player_name)
                        team_pattern = rf'(\*\*{player_pattern}\*\*)\s*\(([^)]+)\)'
                        
                        def replace_team(match):
                            player_part = match.group(1)
                            current_team = match.group(2).strip()
                            
                            # Determine replacement team
                            if new_team in ["trasferito", "nuovo club", "nuovo team"]:
                                replacement_team = "nuovo club"
                            else:
                                replacement_team = new_team
                                
                            applied_corrections.append(f"Corrected {player_name}: {current_team} → {replacement_team}")
                            return f"{player_part} ({replacement_team})"

                        # Apply the correction
                        new_text = re.sub(team_pattern, replace_team, corrected_text, flags=re.IGNORECASE)
                        if new_text != corrected_text:
                            corrected_text = new_text
                            continue
                        
                        # Pattern 2: More general pattern for any team name in parentheses after player
                        general_pattern = rf'({re.escape(player_name)})\s*\(([^)]+)\)'
                        
                        def replace_general_team(match):
                            player_part = match.group(1)
                            current_team = match.group(2).strip()
                            
                            if new_team in ["trasferito", "nuovo club", "nuovo team"]:
                                replacement_team = "nuovo club"
                            else:
                                replacement_team = new_team
                                
                            applied_corrections.append(f"Corrected {player_name}: {current_team} → {replacement_team}")
                            return f"{player_part} ({replacement_team})"
                        
                        corrected_text = re.sub(general_pattern, replace_general_team, corrected_text, flags=re.IGNORECASE)

            except Exception as e:
                logger.error(f"Error applying single correction: {e}")

        return corrected_text, applied_corrections

    def get_recent_corrections(self, limit: int = 20) -> List[Dict]:
        """Get most recent corrections"""
        if not self.knowledge_manager:
            return []

        try:
            where_filter = {"type": {"$eq": "correction"}}
            results = self.knowledge_manager.search_knowledge(
                text=None,
                where=where_filter,
                n_results=limit,
                include=["metadatas"]
            )

            corrections = []
            if results and "metadatas" in results:
                metadatas = results["metadatas"]
                # Handle both single query and multiple query results
                if isinstance(metadatas[0], list):
                    metadatas = metadatas[0]
                
                for metadata in metadatas:
                    if metadata and metadata.get("type") == "correction":
                        corrections.append(metadata)

            # Sort by creation time (most recent first)
            corrections.sort(
                key=lambda x: x.get("created_at", ""),
                reverse=True
            )

            return corrections[:limit]

        except Exception as e:
            logger.error(f"Failed to get recent corrections: {e}")
            return []

    def search_knowledge(self, query: str, n_results: int = 10):
        """Search corrections using knowledge manager"""
        return self.get_relevant_corrections(query, n_results)

    def get_corrections(self, limit: int = 50) -> List[Dict]:
        """Get all corrections"""
        return self.get_recent_corrections(limit)

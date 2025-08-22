import json
import logging
import re
import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

class CorrectionsManager:
    """Enhanced corrections manager with better retrieval and application"""

    def __init__(self, knowledge_manager=None):
        self.knowledge_manager = knowledge_manager
        self._correction_cache = {}  # Cache for faster lookups
        self.db_path = "corrections.db"
        self._init_db()
        self.current_season = "2024-25"

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

                # Try to extract player and team info from correction fields
                wrong_info = wrong.strip()
                correct_info = correct.strip()

                # Extract player name (should be in both wrong and correct)
                player_match = re.search(r'^(\w+(?:\s+\w+)*)\s+team:', wrong_info)
                if not player_match:
                    continue

                player_name = player_match.group(1).strip()

                # Check if this player appears in the text
                if player_name.lower() not in corrected_text.lower():
                    continue

                # Extract old and new team info
                old_team_match = re.search(r'team:\s*(.+?)(?:\s*->|\s*$)', wrong_info)
                new_team_match = re.search(r'team:\s*(.+?)(?:\s*->|\s*$)', correct_info)

                if not (old_team_match and new_team_match):
                    continue

                old_team = old_team_match.group(1).strip()
                new_team = new_team_match.group(1).strip()

                # Determine the replacement team
                if new_team in ["trasferito", "nuovo club", "nuovo team"]:
                    replacement_team = "nuovo club"
                else:
                    replacement_team = new_team

                # Pattern 1: "**Player Name** (Team)" format
                player_pattern = re.escape(player_name)
                team_pattern = rf'(\*\*{player_pattern}\*\*)\s*\(([^)]+)\)'

                def replace_team(match):
                    player_part = match.group(1)
                    current_team = match.group(2).strip()
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

    def _init_db(self):
        """Initialize SQLite database for persistent corrections"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Drop and recreate table to fix schema issues
                conn.execute("DROP TABLE IF EXISTS corrections")
                conn.execute("""
                    CREATE TABLE corrections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_name TEXT NOT NULL,
                        correction_type TEXT NOT NULL,
                        old_value TEXT,
                        new_value TEXT NOT NULL,
                        season TEXT DEFAULT '2024-25',
                        persistent BOOLEAN DEFAULT TRUE,
                        applied BOOLEAN DEFAULT FALSE,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Data quality issues table
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS data_issues (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        issue_type TEXT NOT NULL,
                        description TEXT,
                        severity TEXT DEFAULT 'medium',
                        status TEXT DEFAULT 'open',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Current active players table (for quick filtering)
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS active_players (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_name TEXT NOT NULL UNIQUE,
                        team TEXT NOT NULL,
                        role TEXT,
                        season TEXT DEFAULT '2024-25',
                        is_active BOOLEAN DEFAULT TRUE,
                        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
                
                # Add missing columns if they don't exist (for existing databases)
                try:
                    conn.execute("ALTER TABLE corrections ADD COLUMN correction_type TEXT")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute("ALTER TABLE corrections ADD COLUMN season TEXT DEFAULT '2024-25'")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                    
                try:
                    conn.execute("ALTER TABLE corrections ADD COLUMN persistent BOOLEAN DEFAULT TRUE")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                    
                try:
                    conn.execute("ALTER TABLE corrections ADD COLUMN applied BOOLEAN DEFAULT FALSE")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                    
                try:
                    conn.execute("ALTER TABLE corrections ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                    
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to initialize corrections database: {e}")

    def add_persistent_correction(self, player_name: str, field_name: str, 
                                old_value: str, new_value: str, reason: str = None):
        """Add correction to persistent database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO corrections (player_name, field_name, old_value, new_value, reason)
                    VALUES (?, ?, ?, ?, ?)
                """, (player_name, field_name, old_value, new_value, reason))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to add persistent correction: {e}")
            return False

    def get_persistent_corrections(self, limit: int = 50) -> List[Dict]:
        """Get corrections from persistent database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT player_name, field_name, old_value, new_value, reason, created_at
                    FROM corrections 
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (limit,))

                corrections = []
                for row in cursor.fetchall():
                    corrections.append({
                        "player_name": row[0],
                        "field_name": row[1], 
                        "old_value": row[2],
                        "new_value": row[3],
                        "reason": row[4],
                        "created_at": row[5]
                    })
                return corrections
        except Exception as e:
            logger.error(f"Failed to get persistent corrections: {e}")
            return []

    def add_correction_to_db(self, player_name: str, correction_type: str, old_value: str = None, new_value: str = None, persistent: bool = True):
        """Add correction to the database, with options for persistence and current season."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check table schema first
                cursor.execute("PRAGMA table_info(corrections)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'player_name' in columns:
                    cursor.execute('''
                        INSERT INTO corrections (player_name, correction_type, old_value, new_value, season, persistent)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (player_name, correction_type, old_value, new_value, self.current_season, persistent))
                else:
                    # Use alternative column names if schema is different
                    cursor.execute('''
                        INSERT INTO corrections (field_name, old_value, new_value, reason, created_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (player_name, old_value or correction_type, new_value, f"{correction_type}: {player_name}"))
                
                conn.commit()
                logger.info(f"Added correction to DB: {player_name} - {correction_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to add correction: {e}")
            return False

    def get_corrections(self, applied: bool = None, persistent_only: bool = True):
        """Retrieve corrections, with options to filter by applied status and persistence."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = 'SELECT * FROM corrections WHERE 1=1'
        params = []

        if applied is not None:
            query += ' AND applied = ?'
            params.append(applied)

        if persistent_only:
            query += ' AND persistent = TRUE'
        
        query += ' ORDER BY timestamp DESC'

        cursor.execute(query, params)
        corrections = cursor.fetchall()
        conn.close()
        return corrections

    def mark_applied(self, correction_id: int):
        """Mark a specific correction as applied."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE corrections SET applied = TRUE WHERE id = ?', (correction_id,))
        conn.commit()
        conn.close()

    def remove_player(self, player_name: str, reason: str = "User request"):
        """Permanently remove a player from all recommendations."""
        try:
            # Add to corrections database with persistent flag
            success = self.add_correction_to_db(player_name, "REMOVE", None, "EXCLUDED", persistent=True)
            
            # Also add to knowledge manager for immediate effect
            if self.knowledge_manager:
                correction_text = f"PLAYER_REMOVED: {player_name} - Reason: {reason}"
                metadata = {
                    "type": "player_removal",
                    "player_name": player_name,
                    "action": "REMOVE",
                    "reason": reason,
                    "created_at": datetime.now().isoformat(),
                    "persistent": True
                }
                
                import uuid
                doc_id = str(uuid.uuid4())
                self.knowledge_manager.collection.add(
                    documents=[correction_text],
                    metadatas=[metadata],
                    ids=[doc_id]
                )
            
            if success:
                self.log_data_issue("PLAYER_REMOVAL", f"Player {player_name} removed: {reason}", "high")
                # Force immediate application by clearing any cached data
                self._clear_correction_cache()
                logger.info(f"Successfully removed player {player_name} persistently")
                return f"✅ {player_name} è stato rimosso permanentemente da tutte le raccomandazioni (persistente tra sessioni)."
            else:
                return f"❌ Errore nel rimuovere {player_name} dal database."
        except Exception as e:
            logger.error(f"Error in remove_player for {player_name}: {e}")
            return f"❌ Errore nel rimuovere {player_name}: {e}"

    def update_player_team(self, player_name: str, old_team: str, new_team: str):
        """Update player's team affiliation and log the change."""
        self.add_correction_to_db(player_name, "TEAM_UPDATE", old_team, new_team, persistent=True)
        self.update_active_player(player_name, new_team)
        return f"Updated {player_name}: {old_team} → {new_team}"

    def update_active_player(self, player_name: str, team: str, role: str = None):
        """Update or insert active player data, marking them as active for the current season."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO active_players (player_name, team, role, season, is_active, last_updated)
            VALUES (?, ?, ?, ?, TRUE, CURRENT_TIMESTAMP)
        ''', (player_name, team, role, self.current_season))

        conn.commit()
        conn.close()

    def deactivate_player(self, player_name: str):
        """Mark a player as inactive in the active_players table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE active_players SET is_active = FALSE WHERE player_name = ?', (player_name,))
        conn.commit()
        conn.close()

    def log_data_issue(self, issue_type: str, description: str, severity: str = "medium"):
        """Log data quality issues for tracking and reporting."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO data_issues (issue_type, description, severity)
            VALUES (?, ?, ?)
        ''', (issue_type, description, severity))
        conn.commit()
        conn.close()

    def get_excluded_players(self):
        """Retrieve a list of player names marked for exclusion."""
        # Use cached version if available
        if hasattr(self, '_excluded_players_cache'):
            return self._excluded_players_cache
            
        # Fetch all persistent corrections from database
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if the table exists and get its schema
                cursor.execute("PRAGMA table_info(corrections)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if not columns:
                    # Table doesn't exist yet
                    self._excluded_players_cache = []
                    return []
                
                # Use the correct column name based on the schema
                if 'player_name' in columns:
                    player_col = 'player_name'
                elif 'name' in columns:
                    player_col = 'name'
                else:
                    # Fallback: get the first text column
                    cursor.execute("SELECT * FROM corrections LIMIT 1")
                    if cursor.fetchone():
                        player_col = columns[1] if len(columns) > 1 else columns[0]
                    else:
                        self._excluded_players_cache = []
                        return []
                
                # Query with the correct column name
                if 'correction_type' in columns:
                    cursor.execute(f"""
                        SELECT {player_col} FROM corrections 
                        WHERE correction_type = 'REMOVE' 
                        AND new_value = 'EXCLUDED' 
                        AND persistent = TRUE
                    """)
                else:
                    # Fallback for older schema
                    cursor.execute(f"""
                        SELECT {player_col} FROM corrections 
                        WHERE old_value IS NULL 
                        AND new_value = 'EXCLUDED'
                    """)
                
                excluded = [row[0] for row in cursor.fetchall()]
                
                # Cache the result
                self._excluded_players_cache = excluded
                return excluded
        except Exception as e:
            logger.error(f"Error retrieving excluded players: {e}")
            return []

    def apply_corrections_to_data(self, players_data: list):
        """Apply all persistent corrections and filters to a list of player dictionaries."""
        excluded_players = set(self.get_excluded_players())
        corrections = self.get_corrections(persistent_only=True)

        # Build correction maps for efficient lookup (case-insensitive)
        team_updates = {}
        for correction in corrections:
            if len(correction) > 4:
                player_name, correction_type, old_value, new_value = correction[1], correction[2], correction[3], correction[4]
                if correction_type == "TEAM_UPDATE":
                    # Store with lowercase key for matching, but preserve original case for new value
                    team_updates[player_name.lower()] = new_value

        # Apply corrections and filters
        filtered_data = []
        for player in players_data:
            # Create a copy to avoid modifying the original
            player = dict(player)
            player_name = player.get("name", "")
            player_name_lower = player_name.lower()

            # Skip players marked for exclusion (case-insensitive matching)
            if any(player_name_lower == excluded.lower() for excluded in excluded_players):
                continue

            # Apply team updates if available (case-insensitive matching)
            if player_name_lower in team_updates:
                new_team = team_updates[player_name_lower]
                old_team = player.get("team", "Unknown")
                player["team"] = new_team
                # Log the team update being applied
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Applied persistent team update: {player_name} {old_team} -> {new_team}")

            # Filter to include only Serie A teams for the current season
            if self.is_serie_a_team(player.get("team", "")):
                filtered_data.append(player)

        return filtered_data

    def _clear_correction_cache(self):
        """Clear any internal correction caches to force fresh data loading."""
        self._correction_cache = {}
        # Force re-initialization of any cached data
        if hasattr(self, '_excluded_players_cache'):
            delattr(self, '_excluded_players_cache')

    def is_serie_a_team(self, team: str) -> bool:
        """Check if a given team name is part of the current Serie A league."""
        if not team:
            return False
            
        team_norm = team.lower().strip()
        
        # Current Serie A 2024-25 teams
        serie_a_teams = {
            "atalanta", "bologna", "cagliari", "como", "empoli", "fiorentina",
            "genoa", "inter", "juventus", "lazio", "lecce", "milan",
            "monza", "napoli", "parma", "roma", "torino", "udinese",
            "venezia", "verona", "hellas verona"
        }
        
        # Handle common variations and full names
        team_mappings = {
            "hellas verona": "verona",
            "ac milan": "milan",
            "fc inter": "inter", 
            "internazionale": "inter",
            "inter milan": "inter",
            "juventus fc": "juventus",
            "as roma": "roma",
            "ss lazio": "lazio",
            "ssc napoli": "napoli",
            "atalanta bc": "atalanta",
            "bologna fc": "bologna",
            "cagliari calcio": "cagliari",
            "como 1907": "como",
            "empoli fc": "empoli",
            "acf fiorentina": "fiorentina",
            "genoa cfc": "genoa",
            "us lecce": "lecce",
            "ac monza": "monza",
            "parma calcio": "parma",
            "torino fc": "torino",
            "udinese calcio": "udinese",
            "venezia fc": "venezia",
            # International teams that should be excluded
            "newcastle": False,
            "newcastle united": False,
            "psg": False,
            "paris saint-germain": False,
            "al hilal": False,
            "tottenham": False,
            "tottenham hotspur": False,
            "arsenal": False,
            "manchester united": False,
            "manchester city": False,
            "chelsea": False,
            "liverpool": False,
            "real madrid": False,
            "barcelona": False,
            "atletico madrid": False,
            "bayern munich": False,
            "borussia dortmund": False
        }
        
        # Check direct exclusions first
        if team_mappings.get(team_norm) is False:
            return False
            
        # Check direct match
        if team_norm in serie_a_teams:
            return True
            
        # Check mappings
        mapped_team = team_mappings.get(team_norm)
        if mapped_team and mapped_team in serie_a_teams:
            return True
            
        return False

    def get_corrected_name(self, name: str) -> Optional[str]:
        """Get the corrected name for a player if one exists"""
        try:
            corrections = self.get_corrections(persistent_only=True)
            for correction in corrections:
                if len(correction) > 4 and correction[2] == "NAME_UPDATE" and correction[1] == name:
                    return correction[4]  # new_value
            return None
        except Exception as e:
            logger.error(f"Error getting corrected name for {name}: {e}")
            return None

    def get_corrected_team(self, player_name: str, current_team: str) -> Optional[str]:
        """Get the corrected team for a player if one exists"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if the table exists and get its schema
                cursor.execute("PRAGMA table_info(corrections)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if not columns:
                    return None
                
                # Query for team corrections for this player
                if 'player_name' in columns and 'correction_type' in columns:
                    cursor.execute("""
                        SELECT new_value FROM corrections 
                        WHERE player_name = ? 
                        AND correction_type = 'TEAM_UPDATE' 
                        AND persistent = TRUE 
                        ORDER BY timestamp DESC 
                        LIMIT 1
                    """, (player_name,))
                else:
                    # Fallback for older schema
                    cursor.execute("""
                        SELECT new_value FROM corrections 
                        WHERE field_name = ? 
                        ORDER BY created_at DESC 
                        LIMIT 1
                    """, (player_name,))
                
                result = cursor.fetchone()
                if result:
                    logger.info(f"Found team correction for {player_name}: {current_team} → {result[0]}")
                    return result[0]
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting corrected team for {player_name}: {e}")
            return None

    def get_data_quality_report(self):
        """Generate a comprehensive report on data quality issues and corrections."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Count open issues by type and severity
        cursor.execute('''
            SELECT issue_type, severity, COUNT(*) as count
            FROM data_issues 
            WHERE status = 'open'
            GROUP BY issue_type, severity
        ''')
        issues = cursor.fetchall()

        # Count total persistent corrections made
        cursor.execute('SELECT COUNT(*) FROM corrections WHERE persistent = TRUE')
        corrections_count = cursor.fetchone()[0]

        conn.close()

        # Return a dictionary summarizing the data quality status
        return {
            "issues_by_type": issues,
            "total_corrections": corrections_count,
            "excluded_players": len(self.get_excluded_players())
        }
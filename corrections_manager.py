
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Any, Optional
import hashlib

class CorrectionsManager:
    def __init__(self, db_path="corrections.db"):
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        """Initialize the corrections database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create corrections table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correction_type TEXT NOT NULL,
                incorrect_info TEXT NOT NULL,
                correct_info TEXT NOT NULL,
                context TEXT,
                confidence_score REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                times_applied INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        # Create player data corrections table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT NOT NULL,
                reason TEXT,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        # Create response patterns table for common hallucinations
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS response_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_text TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                replacement_text TEXT NOT NULL,
                regex_pattern TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Corrections database initialized")
    
    def add_correction(self, correction_type: str, incorrect_info: str, 
                      correct_info: str, context: str = None, 
                      confidence_score: float = 1.0) -> int:
        """Add a new correction to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO corrections 
            (correction_type, incorrect_info, correct_info, context, confidence_score)
            VALUES (?, ?, ?, ?, ?)
        ''', (correction_type, incorrect_info, correct_info, context, confidence_score))
        
        correction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✅ Added correction #{correction_id}: {correction_type}")
        return correction_id
    
    def add_player_correction(self, player_name: str, field_name: str, 
                            old_value: str, new_value: str, 
                            reason: str = None, source: str = None) -> int:
        """Add a player data correction"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO player_corrections 
            (player_name, field_name, old_value, new_value, reason, source)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (player_name, field_name, old_value, new_value, reason, source))
        
        correction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✅ Added player correction for {player_name}: {field_name}")
        return correction_id
    
    def add_response_pattern(self, pattern_text: str, pattern_type: str, 
                           replacement_text: str, regex_pattern: str = None) -> int:
        """Add a response pattern correction"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO response_patterns 
            (pattern_text, pattern_type, replacement_text, regex_pattern)
            VALUES (?, ?, ?, ?)
        ''', (pattern_text, pattern_type, replacement_text, regex_pattern))
        
        pattern_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✅ Added response pattern: {pattern_type}")
        return pattern_id
    
    def apply_corrections(self, text: str, correction_type: str = None) -> str:
        """Apply corrections to text based on stored corrections"""
        corrected_text = text
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Apply general corrections
        if correction_type:
            cursor.execute('''
                SELECT incorrect_info, correct_info, id 
                FROM corrections 
                WHERE correction_type = ? AND status = 'active'
                ORDER BY confidence_score DESC
            ''', (correction_type,))
        else:
            cursor.execute('''
                SELECT incorrect_info, correct_info, id 
                FROM corrections 
                WHERE status = 'active'
                ORDER BY confidence_score DESC
            ''')
        
        corrections = cursor.fetchall()
        applied_corrections = []
        
        for incorrect, correct, correction_id in corrections:
            if incorrect.lower() in corrected_text.lower():
                # Case-insensitive replacement
                import re
                corrected_text = re.sub(re.escape(incorrect), correct, corrected_text, flags=re.IGNORECASE)
                applied_corrections.append(correction_id)
        
        # Apply response patterns
        cursor.execute('''
            SELECT pattern_text, replacement_text, regex_pattern, id 
            FROM response_patterns 
            WHERE status = 'active'
        ''')
        
        patterns = cursor.fetchall()
        for pattern_text, replacement, regex_pattern, pattern_id in patterns:
            if regex_pattern:
                import re
                corrected_text = re.sub(regex_pattern, replacement, corrected_text)
            else:
                corrected_text = corrected_text.replace(pattern_text, replacement)
            
            if pattern_text in text and pattern_text not in corrected_text:
                applied_corrections.append(f"pattern_{pattern_id}")
        
        # Update usage statistics
        for correction_id in applied_corrections:
            if not str(correction_id).startswith("pattern_"):
                cursor.execute('''
                    UPDATE corrections 
                    SET times_applied = times_applied + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (correction_id,))
        
        conn.commit()
        conn.close()
        
        if applied_corrections:
            print(f"📝 Applied {len(applied_corrections)} corrections")
        
        return corrected_text
    
    def get_player_corrections(self, player_name: str = None) -> List[Dict]:
        """Get player corrections"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if player_name:
            cursor.execute('''
                SELECT * FROM player_corrections 
                WHERE player_name = ? AND status = 'active'
                ORDER BY created_at DESC
            ''', (player_name,))
        else:
            cursor.execute('''
                SELECT * FROM player_corrections 
                WHERE status = 'active'
                ORDER BY created_at DESC
            ''')
        
        corrections = []
        for row in cursor.fetchall():
            corrections.append({
                'id': row[0],
                'player_name': row[1],
                'field_name': row[2],
                'old_value': row[3],
                'new_value': row[4],
                'reason': row[5],
                'source': row[6],
                'created_at': row[7],
                'status': row[8]
            })
        
        conn.close()
        return corrections
    
    def correct_player_data(self, player_data: Dict) -> Dict:
        """Apply corrections to player data"""
        if 'name' not in player_data:
            return player_data
        
        corrected_data = player_data.copy()
        player_name = player_data['name']
        
        corrections = self.get_player_corrections(player_name)
        
        for correction in corrections:
            field_name = correction['field_name']
            new_value = correction['new_value']
            
            if field_name in corrected_data:
                # Try to convert to appropriate type
                try:
                    if isinstance(corrected_data[field_name], (int, float)):
                        corrected_data[field_name] = float(new_value) if '.' in new_value else int(new_value)
                    else:
                        corrected_data[field_name] = new_value
                except ValueError:
                    corrected_data[field_name] = new_value
        
        return corrected_data
    
    def get_corrections_summary(self) -> Dict:
        """Get a summary of all corrections"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Count corrections by type
        cursor.execute('''
            SELECT correction_type, COUNT(*), SUM(times_applied) 
            FROM corrections 
            WHERE status = 'active' 
            GROUP BY correction_type
        ''')
        general_corrections = cursor.fetchall()
        
        # Count player corrections
        cursor.execute('''
            SELECT COUNT(*) FROM player_corrections WHERE status = 'active'
        ''')
        player_corrections_count = cursor.fetchone()[0]
        
        # Count response patterns
        cursor.execute('''
            SELECT COUNT(*) FROM response_patterns WHERE status = 'active'
        ''')
        patterns_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'general_corrections': general_corrections,
            'player_corrections_count': player_corrections_count,
            'response_patterns_count': patterns_count,
            'total_corrections': len(general_corrections) + player_corrections_count + patterns_count
        }
    
    def export_corrections(self, export_path: str = "corrections_backup.json"):
        """Export all corrections to JSON file"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all corrections
        cursor.execute('SELECT * FROM corrections')
        general = [dict(zip([col[0] for col in cursor.description], row)) 
                  for row in cursor.fetchall()]
        
        cursor.execute('SELECT * FROM player_corrections')
        player = [dict(zip([col[0] for col in cursor.description], row)) 
                 for row in cursor.fetchall()]
        
        cursor.execute('SELECT * FROM response_patterns')
        patterns = [dict(zip([col[0] for col in cursor.description], row)) 
                   for row in cursor.fetchall()]
        
        conn.close()
        
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'general_corrections': general,
            'player_corrections': player,
            'response_patterns': patterns
        }
        
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Corrections exported to {export_path}")
    
    def import_corrections(self, import_path: str):
        """Import corrections from JSON file"""
        with open(import_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Import general corrections
        for correction in data.get('general_corrections', []):
            cursor.execute('''
                INSERT INTO corrections 
                (correction_type, incorrect_info, correct_info, context, confidence_score, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (correction['correction_type'], correction['incorrect_info'], 
                 correction['correct_info'], correction.get('context'), 
                 correction.get('confidence_score', 1.0), 'active'))
        
        # Import player corrections
        for correction in data.get('player_corrections', []):
            cursor.execute('''
                INSERT INTO player_corrections 
                (player_name, field_name, old_value, new_value, reason, source, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (correction['player_name'], correction['field_name'], 
                 correction.get('old_value'), correction['new_value'], 
                 correction.get('reason'), correction.get('source'), 'active'))
        
        # Import response patterns
        for pattern in data.get('response_patterns', []):
            cursor.execute('''
                INSERT INTO response_patterns 
                (pattern_text, pattern_type, replacement_text, regex_pattern, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (pattern['pattern_text'], pattern['pattern_type'], 
                 pattern['replacement_text'], pattern.get('regex_pattern'), 'active'))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Corrections imported from {import_path}")

# Initialize default corrections
def setup_default_corrections():
    """Setup some default corrections for common issues"""
    corrections = CorrectionsManager()
    
    # Add some common football corrections
    corrections.add_correction(
        "player_status", 
        "Belotti gioca in Italia", 
        "Belotti non gioca più in Serie A", 
        "Player transfer correction"
    )
    
    corrections.add_correction(
        "player_status", 
        "Chiellini è ancora attivo", 
        "Chiellini si è ritirato dal calcio", 
        "Player retirement correction"
    )
    
    # Add response patterns for common hallucinations
    corrections.add_response_pattern(
        "secondo le ultime informazioni", 
        "uncertainty_phrase", 
        "basandomi sui dati disponibili"
    )
    
    corrections.add_response_pattern(
        "nella stagione attuale", 
        "temporal_reference", 
        "nella stagione 2024-25 (dati più recenti disponibili)"
    )
    
    return corrections

if __name__ == "__main__":
    corrections = setup_default_corrections()
    print("✅ Default corrections setup complete")
    print(corrections.get_corrections_summary())


import os
import logging
from typing import Dict, List, Any, Optional
import zipfile
import xml.etree.ElementTree as ET

LOG = logging.getLogger("document_parser")

class DocumentParser:
    def __init__(self):
        self.supported_formats = ['.docx', '.txt']
    
    def parse_docx(self, file_path: str) -> Dict[str, Any]:
        """Parse a DOCX file and extract text content"""
        try:
            with zipfile.ZipFile(file_path, 'r') as docx:
                # Read the main document XML
                try:
                    document_xml = docx.read('word/document.xml')
                except KeyError:
                    LOG.error("Invalid DOCX file: missing document.xml")
                    return {"error": "Invalid DOCX file format"}
                
                # Parse XML
                root = ET.fromstring(document_xml)
                
                # Extract text content
                text_content = self._extract_text_from_xml(root)
                
                # Try to parse structured rules
                rules_structure = self._parse_rules_structure(text_content)
                
                return {
                    "raw_text": text_content,
                    "structured_rules": rules_structure,
                    "success": True
                }
                
        except Exception as e:
            LOG.error(f"Error parsing DOCX file: {e}")
            return {"error": f"Failed to parse DOCX: {str(e)}"}
    
    def _extract_text_from_xml(self, root) -> str:
        """Extract text from XML elements"""
        # Namespace for Word documents
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        
        paragraphs = []
        for paragraph in root.findall('.//w:p', ns):
            para_text = ""
            for text_elem in paragraph.findall('.//w:t', ns):
                if text_elem.text:
                    para_text += text_elem.text
            if para_text.strip():
                paragraphs.append(para_text.strip())
        
        return "\n".join(paragraphs)
    
    def _parse_rules_structure(self, text: str) -> Dict[str, Any]:
        """Parse the text to extract structured rules"""
        rules = {
            "league_info": {},
            "roster_composition": {},
            "budget_rules": {},
            "scoring_system": {},
            "formation_rules": {"allowed_formations": []},
            "transfer_rules": {"transfer_windows": []},
            "custom_rules": {"notes": [], "house_rules": []}
        }
        
        lines = text.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect section headers
            line_lower = line.lower()
            
            if any(word in line_lower for word in ['lega', 'campionato', 'nome']):
                current_section = 'league_info'
                if 'nome' in line_lower or 'lega' in line_lower:
                    parts = line.split(':')
                    if len(parts) > 1:
                        rules['league_info']['name'] = parts[1].strip()
            
            elif any(word in line_lower for word in ['budget', 'crediti', 'costo']):
                current_section = 'budget_rules'
                # Extract budget numbers
                import re
                numbers = re.findall(r'\d+', line)
                if numbers:
                    if 'totale' in line_lower or 'budget' in line_lower:
                        rules['budget_rules']['total_budget'] = int(numbers[0])
            
            elif any(word in line_lower for word in ['rosa', 'giocatori', 'portieri', 'difensori', 'centrocampisti', 'attaccanti']):
                current_section = 'roster_composition'
                import re
                numbers = re.findall(r'\d+', line)
                if numbers:
                    if 'portieri' in line_lower:
                        rules['roster_composition']['portieri'] = int(numbers[0])
                    elif 'difensori' in line_lower:
                        rules['roster_composition']['difensori'] = int(numbers[0])
                    elif 'centrocampisti' in line_lower:
                        rules['roster_composition']['centrocampisti'] = int(numbers[0])
                    elif 'attaccanti' in line_lower:
                        rules['roster_composition']['attaccanti'] = int(numbers[0])
            
            elif any(word in line_lower for word in ['formazione', 'modulo']):
                current_section = 'formation_rules'
                # Extract formation patterns like 3-5-2, 4-4-2, etc.
                import re
                formations = re.findall(r'\d-\d-\d', line)
                for formation in formations:
                    if formation not in rules['formation_rules']['allowed_formations']:
                        rules['formation_rules']['allowed_formations'].append(formation)
            
            elif any(word in line_lower for word in ['punteggio', 'bonus', 'malus', 'gol', 'assist']):
                current_section = 'scoring_system'
                import re
                numbers = re.findall(r'[+-]?\d+(?:\.\d+)?', line)
                if 'gol' in line_lower and numbers:
                    rules['scoring_system']['bonus_gol'] = float(numbers[0])
                elif 'assist' in line_lower and numbers:
                    rules['scoring_system']['bonus_assist'] = float(numbers[0])
            
            else:
                # Add as custom rule if it contains meaningful content
                if len(line) > 10 and current_section != 'league_info':
                    if line not in rules['custom_rules']['notes']:
                        rules['custom_rules']['notes'].append(line)
        
        return rules
    
    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """Parse a document file based on its extension"""
        if not os.path.exists(file_path):
            return {"error": "File not found"}
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.docx':
            return self.parse_docx(file_path)
        elif file_ext == '.txt':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return {
                    "raw_text": content,
                    "structured_rules": self._parse_rules_structure(content),
                    "success": True
                }
            except Exception as e:
                return {"error": f"Failed to read text file: {str(e)}"}
        else:
            return {"error": f"Unsupported file format: {file_ext}"}

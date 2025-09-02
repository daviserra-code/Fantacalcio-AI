
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script to fix the corrupted season_roster.json file.
Handles encoding issues and missing JSON structure with manual parsing.
"""

import json
import re
import logging

LOG = logging.getLogger("fix_corrupted_roster")
logging.basicConfig(level=logging.INFO)

def fix_encoding_issues(text):
    """Fix common encoding issues in the text."""
    # Common replacements for corrupted UTF-8
    replacements = {
        'Ã­': 'í',
        'Ã¡': 'á', 
        'Ã©': 'é',
        'Ã³': 'ó',
        'Ãº': 'ú',
        'Ã ': 'à',
        'Ã¨': 'è',
        'Ã¬': 'ì',
        'Ã²': 'ò',
        'Ã¹': 'ù',
        'Ã±': 'ñ',
        'Ã§': 'ç',
        'Ã¤': 'ä',
        'Ã¶': 'ö',
        'Ã¼': 'ü',
        'ÃŸ': 'ß',
        'Ã¢': 'â',
        'Ã´': 'ô',
        'Ã®': 'î',
        'Ã»': 'û',
        'Ã¥': 'å',
        'Ã¦': 'æ',
        'Ã¸': 'ø',
        'Å ': 'Š',
        'Å¡': 'š',
        'Å½': 'Ž',
        'Å¾': 'ž',
        'Ä': 'Č',
        'Ä': 'č',
        'Ä': 'Ć',
        'Ä': 'ć',
        'Ä': 'Đ',
        'Ä': 'đ',
        'ÄŒ': 'Č',
        'Ä': 'č',
        'Äž': 'ž',
        'Ä±': 'ı',
        'Ã§': 'ç',
        'Å': 'Š',
        'Å emper': 'Šemper',
        'KatiÄ': 'Katić',
        'KonÃ©': 'Koné',
        'NÃ¡ndez': 'Nández',
        'NicolÃ¡s': 'Nicolás',
        'Å¡iÄ': 'šić',
        'Äž': 'ž',
        'MartÃ­nez': 'Martínez',
        'GonzÃ¡lez': 'González',
        'VÃ¡squez': 'Vásquez',
        'IkonÃ©': 'Ikoné',
        'KouamÃ©': 'Kouamé',
        'GuÃ°mundsson': 'Guðmundsson',
        'MontipÃ²': 'Montipò',
        'ViÃ±a': 'Viña',
        'MilenkoviÄ': 'Milenković',
        'ÃalhanoÄlu': 'Çalhanoğlu',
        'BarreÅ¡a': 'Barella',
        'VlahoviÄ': 'Vlahović',
        'YÄ±ldÄ±z': 'Yıldız',
        'DuÅ¡an': 'Dušan',
        'MaruÅ¡iÄ': 'Marušić',
        'MatÃ­as': 'Matías',
        'ValentÃ­n': 'Valentín',
        'KrstoviÄ': 'Krstović',
        'RÃ©mi': 'Rémi',
        'LeÃ£o': 'Leão',
        'ÃstigÃ¥rd': 'Østigård',
        'MilinkoviÄ-SaviÄ': 'Milinković-Savić',
        'ÄuriÄ': 'Đurić',
        'PaweÅ': 'Paweł',
        'VlaÅ¡iÄ': 'Vlašić',
        'DuvÃ¡n': 'Duvàn',
        'NehuÃ©n': 'Nehuen',
        'PÃ©rez': 'Pérez',
        'NicolÃ²': 'Nicolò',
        'ErliÄ': 'Erlić',
        'LaurientÃ©': 'Laurienté',
        'AgustÃ­n': 'Agustín',
        'MihÄilÄ': 'Mihăilă',
        'TourÃ©': 'Touré',
        'BradariÄ': 'Bradarić',
        'SamardÅ¾iÄ': 'Samardžić',
        'KjerrumgÃ¥rd': 'Kjerrumgaard',
        'SÃ¸rensen': 'Sørensen',
        'OrdÃ³Ã±ez': 'Ordóñez',
        'BrescianÃni': 'Brescianini',
        'GutiÃ©rrez': 'Gutiérrez',
        'ConceiÃ§Ã£o': 'Conceição',
        'MÃ¡rio': 'Mário',
        'Rovelle': 'Rovella',
        'DjalÃ³': 'Djaló',
        'KostiÄ': 'Kostić',
        'FagiÃ³li': 'Fagioli',
        'LindstrÃ¸m': 'Lindstrøm',
        'BernabÃ©': 'Bernabé'
    }
    
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    
    return text

def manual_fix_json(content):
    """Manually fix the JSON structure by reconstructing it properly."""
    LOG.info("Attempting manual JSON reconstruction...")
    
    # Fix encoding first
    content = fix_encoding_issues(content)
    
    # The file starts with "  }," - we need to find complete JSON objects
    # Let's split by lines and reconstruct
    lines = content.split('\n')
    
    # Remove empty lines and strip whitespace
    lines = [line.strip() for line in lines if line.strip()]
    
    # Initialize our JSON array
    result_objects = []
    current_object = {}
    current_key = None
    brace_count = 0
    in_object = False
    
    # Start with opening bracket
    fixed_content = "[\n"
    
    for i, line in enumerate(lines):
        # Skip the first line if it starts with "}," (the corrupted part)
        if i == 0 and line.startswith('},'):
            continue
            
        # Count braces to track object boundaries
        open_braces = line.count('{')
        close_braces = line.count('}')
        
        # If we find an opening brace, we're starting a new object
        if '{' in line and not in_object:
            in_object = True
            brace_count = open_braces - close_braces
            fixed_content += "  {\n"
            continue
        elif in_object:
            brace_count += open_braces - close_braces
            
            # Add the line to our fixed content
            if line.strip() and not line.startswith('},'):
                # Ensure proper indentation
                if not line.startswith('  '):
                    line = '    ' + line.strip()
                fixed_content += line + '\n'
                
                # Check if this closes the object
                if brace_count <= 0 and '}' in line:
                    # This object is complete
                    in_object = False
                    brace_count = 0
                    # Add comma except for the last object (we'll fix this later)
                    if not line.endswith(','):
                        fixed_content = fixed_content.rstrip() + ',\n'
                    fixed_content += "  },\n"
    
    # Remove the last comma and close the array
    fixed_content = fixed_content.rstrip().rstrip(',') + '\n]'
    
    return fixed_content

def main():
    corrupted_file = "season_roster.json.corrupted.1756762135"
    output_file = "season_roster.json"
    
    try:
        # Read the corrupted file
        with open(corrupted_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        LOG.info(f"Read corrupted file: {len(content)} characters")
        
        # Try manual reconstruction first
        try:
            fixed_content = manual_fix_json(content)
            LOG.info("Manual reconstruction completed")
            
            # Test if the fixed content is valid JSON
            data = json.loads(fixed_content)
            LOG.info(f"Successfully parsed JSON with {len(data)} records")
            
        except (json.JSONDecodeError, Exception) as e:
            LOG.error(f"Manual reconstruction failed: {e}")
            LOG.info("Falling back to line-by-line extraction...")
            
            # Fallback: Extract individual JSON objects line by line
            content = fix_encoding_issues(content)
            lines = content.split('\n')
            
            objects = []
            current_obj_lines = []
            brace_count = 0
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('},') and not current_obj_lines:
                    continue  # Skip the corrupted first line
                
                current_obj_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                
                if brace_count == 0 and current_obj_lines:
                    # We have a complete object
                    obj_str = '\n'.join(current_obj_lines)
                    obj_str = obj_str.rstrip(',').rstrip()
                    
                    if obj_str.startswith('{') and obj_str.endswith('}'):
                        try:
                            obj = json.loads(obj_str)
                            objects.append(obj)
                        except json.JSONDecodeError:
                            LOG.warning(f"Failed to parse object: {obj_str[:100]}...")
                    
                    current_obj_lines = []
                    brace_count = 0
            
            data = objects
            LOG.info(f"Extracted {len(data)} valid objects")
        
        if not data:
            LOG.error("No valid data extracted")
            return
        
        # Write the fixed file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        LOG.info(f"Successfully fixed and saved {output_file} with {len(data)} players")
        
        # Show some sample data
        if data:
            LOG.info("Sample records:")
            for i, player in enumerate(data[:5]):
                LOG.info(f"  {i+1}. {player.get('name', 'Unknown')} - {player.get('team', 'Unknown')} ({player.get('role', 'Unknown')})")
        
    except Exception as e:
        LOG.error(f"Error fixing corrupted file: {e}")

if __name__ == "__main__":
    main()

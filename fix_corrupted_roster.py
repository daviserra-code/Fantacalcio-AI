
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script to fix the corrupted season_roster.json file.
Handles encoding issues and missing JSON structure.
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
        'MartÃ­nez': 'Martínez',
        'VÃ¡squez': 'Vásquez',
        'GuÃ°mundsson': 'Guðmundsson',
        'MontipÃ²': 'Montipò',
        'ViÃ±a': 'Viña',
        'MilenkoviÄ': 'Milenković',
        'ÃalhanoÄlu': 'Çalhanoğlu',
        'BarreÅ¡a': 'Barella',
        'MartÃ­nez': 'Martínez',
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
        'ViÃ±a': 'Viña',
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
        'GonzÃ¡lez': 'González',
        'MÃ¡rio': 'Mário',
        'Rovelle': 'Rovella',
        'DjalÃ³': 'Djaló',
        'KostiÄ': 'Kostić',
        'FagiÃ³li': 'Fagioli',
        'LindstrÃ¸m': 'Lindstrøm',
        'BernabÃ©': 'Bernabé',
        'Å emper': 'Šemper'
    }
    
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    
    return text

def main():
    corrupted_file = "season_roster.json.corrupted.1756762135"
    output_file = "season_roster.json"
    
    try:
        # Read the corrupted file
        with open(corrupted_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        LOG.info(f"Read corrupted file: {len(content)} characters")
        
        # Fix encoding issues
        content = fix_encoding_issues(content)
        
        # The file seems to be missing the opening bracket, add it
        if not content.strip().startswith('['):
            content = '[' + content
        
        # Ensure proper JSON ending
        if not content.strip().endswith(']'):
            content = content.rstrip().rstrip(',') + '\n]'
        
        # Try to parse the JSON to validate it
        try:
            data = json.loads(content)
            LOG.info(f"Successfully parsed JSON with {len(data)} records")
        except json.JSONDecodeError as e:
            LOG.error(f"JSON parsing failed: {e}")
            # Try to fix common JSON issues
            content = content.replace('}\n  {', '},\n  {')
            content = re.sub(r',(\s*[}\]])', r'\1', content)  # Remove trailing commas
            
            try:
                data = json.loads(content)
                LOG.info(f"Successfully parsed JSON after fixes with {len(data)} records")
            except json.JSONDecodeError as e2:
                LOG.error(f"Could not fix JSON: {e2}")
                return
        
        # Write the fixed file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        LOG.info(f"Successfully fixed and saved {output_file} with {len(data)} players")
        
        # Show some sample data
        if data:
            LOG.info("Sample records:")
            for i, player in enumerate(data[:3]):
                LOG.info(f"  {i+1}. {player.get('name', 'Unknown')} - {player.get('team', 'Unknown')} ({player.get('role', 'Unknown')})")
        
    except Exception as e:
        LOG.error(f"Error fixing corrupted file: {e}")

if __name__ == "__main__":
    main()

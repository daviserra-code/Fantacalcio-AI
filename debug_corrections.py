
<line_number>1</line_number>
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from knowledge_manager import KnowledgeManager
from corrections_manager import CorrectionsManager

def main():
    print("=== CORRECTIONS DEBUG ===")
    
    # Initialize managers
    km = KnowledgeManager()
    cm = CorrectionsManager(knowledge_manager=km)
    
    print(f"ChromaDB collection count: {km.collection.count()}")
    
    # Check for existing corrections
    print("\n=== RECENT CORRECTIONS ===")
    recent_corrections = cm.get_recent_corrections(limit=10)
    
    if recent_corrections:
        for i, corr in enumerate(recent_corrections, 1):
            print(f"{i}. {corr.get('wrong', '')} → {corr.get('correct', '')}")
            print(f"   Created: {corr.get('created_at', '')}")
            print(f"   Context: {corr.get('context', '')}")
            print()
    else:
        print("No corrections found")
    
    # Test correction retrieval for specific queries
    print("\n=== TESTING CORRECTIONS FOR COMMON QUERIES ===")
    test_queries = [
        "Morata",
        "Kvaratskhelia", 
        "Como",
        "Napoli"
    ]
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        relevant = cm.get_relevant_corrections(query, limit=3)
        if relevant:
            for corr in relevant:
                print(f"  - {corr.get('wrong', '')} → {corr.get('correct', '')}")
        else:
            print("  No relevant corrections found")
    
    # Test correction application
    print("\n=== TESTING CORRECTION APPLICATION ===")
    test_texts = [
        "Alvaro Morata gioca nel Milan",
        "Khvicha Kvaratskhelia è un giocatore del Napoli",
        "Il Como ha fatto ottimi acquisti"
    ]
    
    for text in test_texts:
        corrected, applied = cm.apply_corrections_to_text(text)
        print(f"\nOriginal: {text}")
        print(f"Corrected: {corrected}")
        if applied:
            print(f"Applied: {', '.join(applied)}")
        else:
            print("No corrections applied")

if __name__ == "__main__":
    main()

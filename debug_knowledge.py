
#!/usr/bin/env python3

import os
from knowledge_manager import KnowledgeManager
from retrieval.helpers import dump_chroma_texts_ids
from retrieval.rag_pipeline import RAGPipeline

def diagnose_knowledge_base():
    print("🔍 Diagnosing knowledge base...")
    
    # Initialize knowledge manager
    km = KnowledgeManager()
    print(f"📊 Collection count: {km.count()}")
    
    # Sample some documents
    print("\n📄 Sample documents:")
    try:
        results = km.search_knowledge("Osimhen", n_results=3)
        for i, result in enumerate(results):
            print(f"  {i+1}. {result['text'][:100]}...")
            print(f"     Metadata: {result.get('metadata', {})}")
            print()
    except Exception as e:
        print(f"❌ Error searching: {e}")
    
    # Test RAG pipeline
    print("🔄 Testing RAG pipeline...")
    try:
        texts, ids = dump_chroma_texts_ids(km.collection)
        rag = RAGPipeline(km.collection, texts, ids)
        
        # Test query
        result = rag.retrieve("migliori attaccanti", final_k=5)
        print(f"✅ RAG Results: {len(result['results'])} documents")
        print(f"   Grounded: {result['grounded']}")
        print(f"   Has conflicts: {result['has_conflict']}")
        print(f"   Citations: {len(result['citations'])}")
        
        if result['results']:
            print("   First result:")
            first = result['results'][0]
            print(f"     Text: {first.get('text', '')[:100]}...")
            print(f"     Metadata: {first.get('metadata', {})}")
    
    except Exception as e:
        print(f"❌ RAG Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    diagnose_knowledge_base()

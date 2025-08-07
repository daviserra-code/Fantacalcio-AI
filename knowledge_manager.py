
import chromadb
import json
import os
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import uuid

class KnowledgeManager:
    def __init__(self, collection_name="fantacalcio_knowledge"):
        # Initialize ChromaDB client with connection pooling
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.collection_name = collection_name
        
        # Initialize sentence transformer for embeddings
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Query cache for embedding results
        self.query_cache = {}
        self.query_cache_size = 50
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(collection_name)
            # Check if collection is empty
            count = self.collection.count()
            if count == 0:
                print(f"📂 Found empty collection: {collection_name}")
                self.collection_is_empty = True
            else:
                print(f"✅ Loaded existing collection: {collection_name} with {count} documents")
                self.collection_is_empty = False
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "Fantacalcio knowledge base for RAG"}
            )
            print(f"🆕 Created new collection: {collection_name}")
            self.collection_is_empty = True
    
    def add_knowledge(self, text: str, metadata: Dict[str, Any] = None, doc_id: str = None):
        """Add knowledge to the vector database"""
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        # Generate embedding
        embedding = self.encoder.encode(text).tolist()
        
        self.collection.add(
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata or {}],
            ids=[doc_id]
        )
        
        return doc_id
    
    def search_knowledge(self, query: str, n_results: int = 3) -> List[Dict]:
        """Search for relevant knowledge with caching"""
        cache_key = f"{query.lower().strip()}_{n_results}"
        
        # Check query cache first
        if cache_key in self.query_cache:
            return self.query_cache[cache_key]
        
        # Generate query embedding
        query_embedding = self.encoder.encode(query).tolist()
        
        # Search in collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=['documents', 'metadatas', 'distances']
        )
        
        # Format results
        formatted_results = []
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'relevance_score': 1 - results['distances'][0][i]  # Convert distance to similarity
            })
        
        # Cache the results
        if len(self.query_cache) >= self.query_cache_size:
            # Remove oldest cache entry
            oldest_key = next(iter(self.query_cache))
            del self.query_cache[oldest_key]
        
        self.query_cache[cache_key] = formatted_results
        return formatted_results
    
    def load_from_jsonl(self, jsonl_path: str):
        """Load knowledge from JSONL file only if collection is empty"""
        if not self.collection_is_empty:
            print(f"⏭️ Skipping {jsonl_path} - data already loaded in collection")
            return
            
        if not os.path.exists(jsonl_path):
            print(f"❌ JSONL file not found: {jsonl_path}")
            return
        
        count = 0
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    text = data.get('text', '')
                    metadata = data.get('metadata', {})
                    doc_id = data.get('id')
                    
                    if text:
                        self.add_knowledge(text, metadata, doc_id)
                        count += 1
                except json.JSONDecodeError as e:
                    print(f"⚠️ Error parsing line: {e}")
        
        print(f"✅ Loaded {count} knowledge entries from {jsonl_path}")
        self.collection_is_empty = False
    
    def get_context_for_query(self, query: str, max_context_length: int = 1000) -> str:
        """Get relevant context for a query, formatted for LLM input"""
        results = self.search_knowledge(query, n_results=8)
        
        print(f"🧠 Knowledge Manager - Processing {len(results)} results for query: '{query[:50]}...'")
        
        # Use more flexible relevance thresholds - accept more results
        high_quality_results = [r for r in results if r['relevance_score'] > 0.5]
        medium_quality_results = [r for r in results if 0.3 < r['relevance_score'] <= 0.5]
        
        print(f"   High quality (>0.5): {len(high_quality_results)}")
        print(f"   Medium quality (0.3-0.5): {len(medium_quality_results)}")
        
        # If no high quality, try medium quality results
        if not high_quality_results and medium_quality_results:
            high_quality_results = medium_quality_results[:3]
            print(f"   Using {len(high_quality_results)} medium quality results")
        
        # If still no results, take top 2 regardless of score for general context
        if not high_quality_results and results:
            high_quality_results = results[:2]
            print(f"   Fallback: using top {len(high_quality_results)} results regardless of score")
        
        context_parts = []
        current_length = 0
        
        # Sort by relevance score (highest first)
        high_quality_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        for result in high_quality_results:
            text = result['text']
            score = result['relevance_score']
            
            if current_length + len(text) <= max_context_length:
                # Include relevance information for transparency
                context_parts.append(f"- {text} [Rilevanza: {score:.2f}]")
                current_length += len(text)
            else:
                break
        
        if context_parts:
            final_context = "Informazioni verificate dal database:\n" + "\n".join(context_parts)
            print(f"📝 Final context created: {len(final_context)} chars, {len(context_parts)} parts")
            return final_context
        else:
            print(f"❌ No context generated")
            return ""

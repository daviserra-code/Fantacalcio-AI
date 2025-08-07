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

        # Format results with proper similarity calculation
        formatted_results = []
        for i in range(len(results['documents'][0])):
            # ChromaDB uses cosine distance by default, convert to cosine similarity
            distance = results['distances'][0][i]
            cosine_similarity = 1 - distance  # For cosine distance: similarity = 1 - distance
            
            # Log detailed similarity information
            if i < 3:  # Log first 3 results for debugging
                print(f"   Result {i+1}: Distance={distance:.4f}, Cosine Similarity={cosine_similarity:.4f}")
            
            formatted_results.append({
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'relevance_score': cosine_similarity,
                'cosine_similarity': cosine_similarity,
                'distance': distance
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

        # Use cosine similarity thresholds for filtering
        high_quality_results = [r for r in results if r['cosine_similarity'] > 0.4]
        medium_quality_results = [r for r in results if 0.2 < r['cosine_similarity'] <= 0.4]
        low_quality_results = [r for r in results if 0.1 < r['cosine_similarity'] <= 0.2]

        print(f"   High quality (similarity >0.4): {len(high_quality_results)}")
        print(f"   Medium quality (similarity 0.2-0.4): {len(medium_quality_results)}")
        print(f"   Low quality (similarity 0.1-0.2): {len(low_quality_results)}")

        # Log similarity scores for transparency
        for i, result in enumerate(results[:3]):
            sim = result['cosine_similarity']
            print(f"   Top {i+1} similarity: {sim:.4f} - {result['text'][:50]}...")

        # If no high quality, try medium quality results
        if not high_quality_results and medium_quality_results:
            high_quality_results = medium_quality_results[:3]
            print(f"   Using {len(high_quality_results)} medium quality results")

        # If still no results, try low quality ones
        elif not high_quality_results and not medium_quality_results and low_quality_results:
            high_quality_results = low_quality_results[:2]
            print(f"   Using {len(high_quality_results)} low quality results")

        # Last resort: take top 2 regardless of score for general context
        elif not high_quality_results and results:
            high_quality_results = results[:2]
            print(f"   Fallback: using top {len(high_quality_results)} results (similarities: {[r['cosine_similarity']:.3f for r in high_quality_results]})")

        context_parts = []
        current_length = 0

        # Sort by relevance score (highest first)
        high_quality_results.sort(key=lambda x: x['relevance_score'], reverse=True)

        for result in high_quality_results:
            text = result['text']
            score = result['relevance_score']

            if current_length + len(text) <= max_context_length:
                # Include cosine similarity for transparency
                context_parts.append(f"- {text} [Similarity: {score:.3f}]")
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

    def verify_embedding_consistency(self):
        """Verify that embeddings are consistent and high quality"""
        print(f"🔬 EMBEDDING VERIFICATION:")
        
        # Verify model name
        model_name = getattr(self.encoder, 'model_name', 'all-MiniLM-L6-v2')
        print(f"   Model: {model_name}")
        print(f"   Model device: {self.encoder.device}")
        print(f"   Collection: {self.collection_name}")
        print(f"   Total documents: {self.collection.count()}")

        # Test embedding with sample text
        sample_text = "Lautaro Martinez fantamedia gol assist"
        sample_embedding = self.encoder.encode(sample_text).tolist()
        
        # Calculate L2 norm (should be 1.0 for normalized embeddings)
        embedding_norm = (sum(x*x for x in sample_embedding))**0.5

        print(f"   Sample text: '{sample_text}'")
        print(f"   Sample embedding dimensions: {len(sample_embedding)}")
        print(f"   Sample embedding norm: {embedding_norm:.4f}")
        print(f"   Is normalized: {'Yes' if abs(embedding_norm - 1.0) < 0.001 else 'No'}")

        # Test search with the sample and log similarity scores
        print(f"\n🔍 TESTING SEARCH WITH COSINE SIMILARITY:")
        results = self.search_knowledge(sample_text, n_results=5)
        print(f"   Total search results: {len(results)}")

        for i, result in enumerate(results):
            similarity = result['cosine_similarity']
            distance = result['distance']
            print(f"   Result {i+1}:")
            print(f"     Cosine Similarity: {similarity:.4f}")
            print(f"     Distance: {distance:.4f}")
            print(f"     Text: '{result['text'][:60]}...'")
            
            # Check if similarity makes sense (should be between -1 and 1)
            if -1 <= similarity <= 1:
                quality = "Good" if similarity > 0.3 else "Low" if similarity > 0 else "Very Low"
                print(f"     Quality: {quality}")
            else:
                print(f"     WARNING: Invalid similarity score!")

        return len(results) > 0

    def reset_database(self):
        """Reset the entire ChromaDB database and rebuild from scratch"""
        print(f"🗑️ RESETTING DATABASE...")
        
        try:
            # Reset the entire ChromaDB client (clears all collections)
            self.client.reset()
            print("✅ ChromaDB reset complete - all collections cleared")
            
            # Recreate the collection
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Fantacalcio knowledge base for RAG"}
            )
            print(f"✅ Recreated collection: {self.collection_name}")
            
            # Mark collection as empty so data will be reloaded
            self.collection_is_empty = True
            
            # Clear query cache
            self.query_cache = {}
            print("✅ Query cache cleared")
            
            return True
            
        except Exception as e:
            print(f"❌ Error resetting database: {e}")
            return False

    def rebuild_database_from_jsonl(self, jsonl_files):
        """Rebuild database from JSONL files after reset"""
        print(f"🔄 REBUILDING DATABASE...")
        
        total_loaded = 0
        for jsonl_file in jsonl_files:
            if os.path.exists(jsonl_file):
                count = 0
                try:
                    with open(jsonl_file, 'r', encoding='utf-8') as f:
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
                                print(f"⚠️ Error parsing line in {jsonl_file}: {e}")
                    
                    print(f"✅ Loaded {count} entries from {jsonl_file}")
                    total_loaded += count
                    
                except Exception as e:
                    print(f"❌ Error loading {jsonl_file}: {e}")
            else:
                print(f"⚠️ File not found: {jsonl_file}")
        
        self.collection_is_empty = False
        print(f"🎉 Database rebuild complete! Total entries loaded: {total_loaded}")
        return total_loaded
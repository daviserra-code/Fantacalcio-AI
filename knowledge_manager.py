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
            print(f"✅ Loaded existing collection: {collection_name}")
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "Fantacalcio knowledge base for RAG"}
            )
            print(f"🆕 Created new collection: {collection_name}")

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
        """Load knowledge from JSONL file"""
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

    def get_context_for_query(self, query, max_results=3):
        """Get relevant context for a query using similarity search"""
        try:
            # Use similarity search to find relevant documents with timeout
            results = self.collection.query(
                query_texts=[query],
                n_results=max_results
            )

            # Extract and format the relevant context
            contexts = []
            if results['documents']:
                for doc in results['documents'][0][:max_results]:
                    # Limit context length for speed
                    if len(doc) <= 500:
                        contexts.append(doc)

            # Join contexts with newlines, limit total length
            context = "\n".join(contexts[:max_results]) if contexts else ""
            return context[:1000]  # Limit to 1000 chars for speed

        except Exception as e:
            print(f"Error retrieving context: {e}")
            return ""
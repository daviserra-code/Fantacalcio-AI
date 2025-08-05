
import chromadb
import json
import os
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import uuid

class FantacalcioRAGSystem:
    def __init__(self, collection_name="fantacalcio_knowledge"):
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.collection_name = collection_name
        
        # Initialize sentence transformer for embeddings
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=collection_name)
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
    
    def load_jsonl_data(self, jsonl_file_path: str):
        """Load and index data from JSONL file"""
        documents = []
        metadatas = []
        ids = []
        
        with open(jsonl_file_path, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file):
                try:
                    data = json.loads(line.strip())
                    
                    # Extract text content
                    text_content = data.get('text') or data.get('content') or data.get('question', '')
                    if data.get('answer'):
                        text_content += f" {data['answer']}"
                    
                    if text_content:
                        documents.append(text_content)
                        
                        # Create metadata
                        metadata = {
                            "source": jsonl_file_path,
                            "line_number": line_num,
                            "type": data.get('type', 'general')
                        }
                        
                        # Add additional fields from JSONL
                        for key in ['player', 'team', 'role', 'league_type', 'category']:
                            if key in data:
                                metadata[key] = data[key]
                        
                        metadatas.append(metadata)
                        ids.append(str(uuid.uuid4()))
                
                except json.JSONDecodeError:
                    print(f"Error parsing line {line_num} in {jsonl_file_path}")
                    continue
        
        # Add documents to collection
        if documents:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"Loaded {len(documents)} documents from {jsonl_file_path}")
    
    def add_knowledge(self, text: str, metadata: Dict[str, Any] = None):
        """Add single knowledge item"""
        if metadata is None:
            metadata = {}
        
        self.collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[str(uuid.uuid4())]
        )
    
    def search_knowledge(self, query: str, n_results: int = 5, filter_criteria: Dict = None) -> List[Dict]:
        """Search for relevant knowledge"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=filter_criteria
        )
        
        knowledge_items = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                knowledge_items.append({
                    'content': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'distance': results['distances'][0][i] if results['distances'] else 0
                })
        
        return knowledge_items
    
    def get_enhanced_context(self, user_query: str, league_context: Dict = None) -> str:
        """Get enhanced context for AI assistant"""
        # Search for relevant knowledge
        filter_criteria = {}
        if league_context and league_context.get('league_type'):
            filter_criteria['league_type'] = league_context['league_type']
        
        relevant_knowledge = self.search_knowledge(
            user_query, 
            n_results=3, 
            filter_criteria=filter_criteria if filter_criteria else None
        )
        
        # Build context string
        context_parts = []
        if relevant_knowledge:
            context_parts.append("Conoscenze rilevanti dal database:")
            for item in relevant_knowledge:
                context_parts.append(f"- {item['content']}")
        
        return "\n".join(context_parts)
    
    def clear_collection(self):
        """Clear all data from collection"""
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            print(f"Cleared collection {self.collection_name}")
        except Exception as e:
            print(f"Error clearing collection: {e}")

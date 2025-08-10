from retrieval.helpers import dump_chroma_texts_ids  # se l'hai creato
from retrieval.rag_pipeline import RAGPipeline

texts, ids = dump_chroma_texts_ids(self.knowledge_manager.collection)
self.rag = RAGPipeline(self.knowledge_manager.collection, texts, ids)
"""Vector store interface for RAG system. Uses FAISS over parking_info.txt by default."""
from typing import List, Dict, Any, Optional
import numpy as np
from .embeddings import EmbeddingGenerator
from .faiss_store import FAISSStore


class VectorStore:
    """Vector store wrapper for RAG. Backed by FAISS over parking_info.txt chunks."""

    def __init__(
        self,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        use_mock: bool = True,
    ):
        self.embedding_model = embedding_model
        self.use_mock = use_mock
        self._embedding_generator = None
        self._client = None

    @property
    def embedding_generator(self):
        if self._embedding_generator is None:
            self._embedding_generator = EmbeddingGenerator(self.embedding_model)
        return self._embedding_generator

    @property
    def client(self):
        if self._client is None:
            if self.use_mock:
                self._client = FAISSStore(self.embedding_generator)
            else:
                raise NotImplementedError("Real Weaviate client not yet implemented")
        return self._client

    def add_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        if metadatas is None:
            metadatas = [{}] * len(texts)
        embeddings = self.embedding_generator.generate_embeddings(texts)
        documents = [
            {"content": text, "metadata": metadata}
            for text, metadata in zip(texts, metadatas)
        ]
        return self.client.add_documents(documents, embeddings)

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query_embedding = self.embedding_generator.generate_embedding(query)
        return self.client.query(
            query_vector=query_embedding,
            limit=k,
            where=filter
        )

    def get_relevant_context(self, query: str, k: int = 5) -> str:
        results = self.similarity_search(query, k=k)
        if not results:
            return ""
        return "\n".join(f"[{i}] {r['content']}" for i, r in enumerate(results, 1))

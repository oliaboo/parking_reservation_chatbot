"""Embedding generation for vector database"""

from typing import List

import numpy as np

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None


class EmbeddingGenerator:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers is not installed. pip install sentence-transformers"
            )
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()

    def generate_embedding(self, text: str) -> np.ndarray:
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def generate_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return [emb.astype(np.float32) for emb in embeddings]

    def get_dimension(self) -> int:
        return self.dimension

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
    """Wraps a sentence-transformers model to produce embeddings for texts."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers is not installed. pip install sentence-transformers"
            )
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def generate_embedding(self, text: str) -> np.ndarray:
        """Return a single embedding vector for the given text (float32)."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def generate_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Return a list of embedding vectors (float32) for the given texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return [emb.astype(np.float32) for emb in embeddings]

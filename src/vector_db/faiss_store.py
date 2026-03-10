"""
FAISS-backed vector store for RAG. Builds vectors from parking_info.txt, adds them
to a FAISS index, and saves the index to disk for reuse.
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from .embeddings import EmbeddingGenerator

from .parking_info_loader import load_parking_info_chunks

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None

# Default paths under project root / data (index and doc store saved to disk)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FAISS_INDEX_PATH = _PROJECT_ROOT / "data" / "faiss_parking.index"
DEFAULT_FAISS_DOCS_PATH = _PROJECT_ROOT / "data" / "faiss_parking_docs.json"


def _normalize(x: np.ndarray) -> np.ndarray:
    """L2-normalize for cosine similarity via inner product. Supports 1D and 2D."""
    if x.ndim == 1:
        norm = np.linalg.norm(x)
        return (x.astype(np.float32) / norm) if norm >= 1e-8 else x.astype(np.float32)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms = np.where(norms < 1e-8, 1.0, norms)
    return (x.astype(np.float32) / norms)


class FAISSStore:
    """
    Vector store using FAISS. Vectors are created from parking_info.txt chunks,
    added to a FAISS index, and the index is saved to disk for future use.
    On init, loads from disk if present; otherwise builds from parking_info.txt and saves.
    """

    def __init__(
        self,
        embedding_generator: "EmbeddingGenerator",
        index_path: Optional[Path] = None,
        docs_path: Optional[Path] = None,
        force_rebuild: bool = False,
    ):
        if not FAISS_AVAILABLE:
            raise ImportError("faiss is not installed. pip install faiss-cpu")
        self.embedding_generator = embedding_generator
        self._index_path = Path(index_path) if index_path is not None else DEFAULT_FAISS_INDEX_PATH
        self._docs_path = Path(docs_path) if docs_path is not None else DEFAULT_FAISS_DOCS_PATH
        self._index = None
        self._doc_store: List[Dict[str, Any]] = []
        self._build_or_load_index(force_rebuild=force_rebuild)

    def _build_or_load_index(self, force_rebuild: bool = False) -> None:
        if not force_rebuild and self._load_from_disk():
            return
        self._build_index_from_parking_info()
        self._save_to_disk()

    def _load_from_disk(self) -> bool:
        """Load FAISS index and doc store from disk. Returns True if both exist and were loaded."""
        if not self._index_path.exists() or not self._docs_path.exists():
            return False
        try:
            self._index = faiss.read_index(str(self._index_path))
            with open(self._docs_path, "r", encoding="utf-8") as f:
                self._doc_store = json.load(f)
            return True
        except Exception:
            return False

    def _save_to_disk(self) -> None:
        """Save FAISS index and doc store to disk."""
        if self._index is None or not self._doc_store:
            return
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._index_path))
        with open(self._docs_path, "w", encoding="utf-8") as f:
            json.dump(self._doc_store, f, ensure_ascii=False, indent=2)

    def _build_index_from_parking_info(self) -> None:
        """Create vectors from parking_info.txt, add to FAISS index, and fill doc_store."""
        chunks = load_parking_info_chunks()
        if not chunks:
            return
        contents = [c["content"] if isinstance(c["content"], str) else str(c) for c in chunks]
        embeddings = self.embedding_generator.generate_embeddings(contents)
        dim = embeddings[0].shape[0] if hasattr(embeddings[0], "shape") else len(embeddings[0])
        vectors = np.stack([np.asarray(e, dtype=np.float32) for e in embeddings])
        vectors = _normalize(vectors)
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(vectors)
        self._doc_store = [
            {"id": str(i + 1), "content": contents[i], "metadata": chunks[i].get("metadata", {})}
            for i in range(len(contents))
        ]

    def query(
        self,
        query_vector: np.ndarray,
        limit: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return top-k documents by cosine similarity (query_vector assumed normalized)."""
        if self._index is None or not self._doc_store:
            return []
        q = np.asarray(query_vector, dtype=np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        q = _normalize(q)
        scores, indices = self._index.search(q, min(limit, len(self._doc_store)))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            doc = self._doc_store[idx]
            if where:
                if not self._matches_filter(doc, where):
                    continue
            results.append({
                "id": doc["id"],
                "content": doc["content"],
                "metadata": doc["metadata"],
                "score": float(score),
            })
        return results[:limit]

    def _matches_filter(self, doc: Dict[str, Any], where: Dict[str, Any]) -> bool:
        for key, value in where.items():
            if doc.get("metadata", {}).get(key) != value:
                return False
        return True

    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        embeddings: List[np.ndarray],
        save_to_disk: bool = True,
    ) -> List[str]:
        """Append documents and their embeddings to the index; optionally save index to disk."""
        if not self._index or not FAISS_AVAILABLE:
            return []
        start = len(self._doc_store)
        vectors = np.stack([_normalize(np.asarray(e, dtype=np.float32)) for e in embeddings])
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        self._index.add(vectors)
        ids = []
        for i, doc in enumerate(documents):
            doc_id = str(start + i + 1)
            self._doc_store.append({
                "id": doc_id,
                "content": doc.get("content", ""),
                "metadata": doc.get("metadata", {}),
            })
            ids.append(doc_id)
        if save_to_disk:
            self._save_to_disk()
        return ids


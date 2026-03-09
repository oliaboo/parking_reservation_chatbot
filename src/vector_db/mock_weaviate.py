"""Mock Weaviate vector database implementation for development"""

from pathlib import Path
from typing import List, Dict, Optional, Any
import numpy as np

# Path to parking_info.txt (project root)
PARKING_INFO_PATH = Path(__file__).resolve().parent.parent.parent / "parking_info.txt"


def _load_parking_info_chunks() -> List[Dict[str, Any]]:
    """Load parking_info.txt and split into chunks (by double newline or section)."""
    if not PARKING_INFO_PATH.exists():
        # Fallback sample data if file missing
        return [
            {"content": "Parking facility: 24/7. Standard and premium spaces.", "metadata": {"type": "general_info"}},
            {"content": "Rates: standard $5/hour, $30/day; premium $8/hour, $45/day.", "metadata": {"type": "pricing"}},
            {"content": "Location: 123 Main Street, Downtown. Entrance on Oak Avenue.", "metadata": {"type": "location"}},
            {"content": "Reservation: provide nickname and preferred date. Check free spaces first.", "metadata": {"type": "booking"}},
        ]
    text = PARKING_INFO_PATH.read_text(encoding="utf-8")
    chunks = []
    current = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            if current:
                chunks.append(" ".join(current))
                current = []
        else:
            current.append(line)
    if current:
        chunks.append(" ".join(current))
    if not chunks:
        chunks = [text[:500] or "Parking information."]
    return [
        {"content": c, "metadata": {"source": "parking_info.txt"}}
        for c in chunks
    ]


class MockWeaviateClient:
    """Mock implementation of Weaviate client for local development. Uses parking_info.txt."""

    def __init__(self, embedding_generator: Optional[Any] = None):
        """
        Initialize mock database with in-memory storage from parking_info.txt.
        If embedding_generator is provided, use it to embed chunks so similarity search returns relevant results.
        Otherwise use random embeddings (retrieval will be arbitrary).
        """
        self.data: Dict[str, List[Dict[str, Any]]] = {}
        self.embeddings: Dict[str, np.ndarray] = {}
        self.class_name = "ParkingInfo"
        self._embedding_generator = embedding_generator
        self._initialize_from_parking_info()

    def _initialize_from_parking_info(self):
        """Load content from parking_info.txt into mock store. Use real embeddings if generator available."""
        raw_chunks = _load_parking_info_chunks()
        sample_data = []
        contents = []
        for i, ch in enumerate(raw_chunks, 1):
            content = ch["content"] if isinstance(ch["content"], str) else str(ch)
            contents.append(content)
            sample_data.append({
                "id": str(i),
                "content": content,
                "metadata": ch.get("metadata", {}),
            })
        self.data[self.class_name] = sample_data
        if self._embedding_generator is not None:
            try:
                doc_embeddings = self._embedding_generator.generate_embeddings(contents)
                for item, emb in zip(sample_data, doc_embeddings):
                    self.embeddings[item["id"]] = np.asarray(emb, dtype=np.float32)
            except Exception:
                dim = getattr(self._embedding_generator, "dimension", 384) or 384
                for item in sample_data:
                    self.embeddings[item["id"]] = np.random.rand(dim).astype(np.float32)
        else:
            dim = 384
            for item in sample_data:
                self.embeddings[item["id"]] = np.random.rand(dim).astype(np.float32)
    
    def query(
        self,
        query_vector: np.ndarray,
        limit: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query the mock database using vector similarity
        
        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results to return
            where: Optional filter conditions
            
        Returns:
            List of matching documents with scores
        """
        if self.class_name not in self.data:
            return []
        
        results = []
        for item in self.data[self.class_name]:
            # Calculate cosine similarity
            doc_embedding = self.embeddings[item["id"]]
            similarity = np.dot(query_vector, doc_embedding) / (
                np.linalg.norm(query_vector) * np.linalg.norm(doc_embedding) + 1e-8
            )
            
            # Apply filters if provided
            if where:
                if not self._matches_filter(item, where):
                    continue
            
            results.append({
                "content": item["content"],
                "metadata": item["metadata"],
                "score": float(similarity),
                "id": item["id"]
            })
        
        # Sort by similarity score (descending) and return top K
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def _matches_filter(self, item: Dict[str, Any], where: Dict[str, Any]) -> bool:
        """Check if item matches the filter conditions"""
        for key, value in where.items():
            if key in item.get("metadata", {}):
                if item["metadata"][key] != value:
                    return False
        return True
    
    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        embeddings: List[np.ndarray]
    ) -> List[str]:
        """
        Add documents to the mock database
        
        Args:
            documents: List of documents with content and metadata
            embeddings: List of embedding vectors
            
        Returns:
            List of document IDs
        """
        if self.class_name not in self.data:
            self.data[self.class_name] = []
        
        ids = []
        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            doc_id = str(len(self.data[self.class_name]) + 1)
            doc["id"] = doc_id
            self.data[self.class_name].append(doc)
            self.embeddings[doc_id] = embedding
            ids.append(doc_id)
        
        return ids
    
    def delete_all(self):
        """Delete all documents from the database"""
        self.data[self.class_name] = []
        self.embeddings = {}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        count = len(self.data.get(self.class_name, []))
        return {
            "total_documents": count,
            "class_name": self.class_name,
            "embedding_dimension": 384
        }


def get_mock_client(embedding_generator: Optional[Any] = None) -> MockWeaviateClient:
    """Factory function to get mock Weaviate client. Pass embedding_generator so retrieval uses real similarity."""
    return MockWeaviateClient(embedding_generator=embedding_generator)

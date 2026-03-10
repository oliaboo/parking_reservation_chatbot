"""Load and chunk parking_info.txt for RAG (shared by FAISS and mock)."""

from pathlib import Path
from typing import Any, Dict, List

PARKING_INFO_PATH = Path(__file__).resolve().parent.parent.parent / "rag_data" / "parking_info.txt"


def load_parking_info_chunks() -> List[Dict[str, Any]]:
    """Load parking_info.txt and split into chunks by paragraph/section (blank line)."""
    if not PARKING_INFO_PATH.exists():
        return [
            {
                "content": "Parking facility: 24/7. Standard and premium spaces.",
                "metadata": {"source": "fallback"},
            },
            {
                "content": "Rates: standard $5/hour, $30/day; premium $8/hour, $45/day.",
                "metadata": {"source": "fallback"},
            },
            {
                "content": "Location: 123 Main Street, Downtown. Entrance on Oak Avenue.",
                "metadata": {"source": "fallback"},
            },
            {
                "content": "Reservation: provide nickname and preferred date. Check free spaces first.",
                "metadata": {"source": "fallback"},
            },
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
    return [{"content": c, "metadata": {"source": "parking_info.txt"}} for c in chunks]

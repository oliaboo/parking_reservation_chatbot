"""
Evaluation dataset for RAG retrieval.
Each item: query + set of relevant document IDs (from mock Weaviate, 1-based string IDs).
Chunks from parking_info.txt correspond to doc IDs 1, 2, 3, ... (by paragraph/section order).
"""
from typing import List
from dataclasses import dataclass


@dataclass
class EvalItem:
    """Single evaluation item: a query and the doc IDs that are relevant answers."""
    query: str
    relevant_doc_ids: List[str]


# Default dataset: query -> relevant chunk IDs (from parking_info.txt chunk order)
# Chunk 1: title/general, 2: location, 3: parking details (200 spaces), 4: working hours,
# 5: prices, 6: availability, 7: booking, 8: payment, 9: contact
DEFAULT_EVAL_DATASET: List[EvalItem] = [
    EvalItem("How many parking spaces do you have?", ["3"]),
    EvalItem("What is the total number of spaces?", ["3"]),
    EvalItem("Where are you located? What is the address?", ["2"]),
    EvalItem("Location of the parking facility", ["2"]),
    EvalItem("What are the working hours?", ["4"]),
    EvalItem("When is the facility open? 24/7?", ["4"]),
    EvalItem("How do I make a reservation? Booking process", ["7"]),
    EvalItem("How can I reserve a parking space?", ["7"]),
    EvalItem("What payment methods do you accept?", ["8"]),
    EvalItem("Payment options", ["8"]),
    EvalItem("How to contact support?", ["9"]),
    EvalItem("Contact information or phone number", ["9"]),
]

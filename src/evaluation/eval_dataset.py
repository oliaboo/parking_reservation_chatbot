"""
Evaluation dataset for RAG retrieval.
Each item: query + set of relevant document IDs (from mock Weaviate, 1-based string IDs).
Chunks from parking_info.txt correspond to doc IDs 1, 2, 3, ... (by paragraph/section order).

parking_info.txt chunk layout:
  1: title; 2-4: location; 5-7: parking details; 8-10: working hours; 11-13: prices;
  14-16: availability; 17-19: booking; 20-22: payment; 23-25: contact;
  26-27: accessibility; 28-29: EV charging; 30: security; 31: bicycle/motorbike;
  32: lost and found; 33: loyalty; 34: group/event; 35-38: stay, weather, conduct, maintenance.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class EvalItem:
    """Single evaluation item: a query and the doc IDs that are relevant answers."""

    query: str
    relevant_doc_ids: List[str]


# Chunk ID ranges: location 2-4, parking 5-7, hours 8-10, prices 11-13,
# availability 14-16, booking 17-19, payment 20-22, contact 23-25
DEFAULT_EVAL_DATASET: List[EvalItem] = [
    EvalItem("How many parking spaces do you have?", ["5", "6", "7"]),
    EvalItem("What is the total number of spaces?", ["5", "6", "7"]),
    EvalItem("Where are you located? What is the address?", ["2", "3", "4"]),
    EvalItem("Location of the parking facility", ["2", "3", "4"]),
    EvalItem("How do I get to the parking? Public transport?", ["2", "3", "4"]),
    EvalItem("What are the working hours?", ["8", "9", "10"]),
    EvalItem("When is the facility open? 24/7?", ["8", "9", "10"]),
    EvalItem("When is the desk staffed? Holiday hours?", ["8", "9", "10"]),
    EvalItem("How do I make a reservation? Booking process", ["17", "18", "19"]),
    EvalItem("How can I reserve a parking space?", ["17", "18", "19"]),
    EvalItem("Reservation rules and cancellation", ["17", "18", "19"]),
    EvalItem("What payment methods do you accept?", ["20", "21", "22"]),
    EvalItem("Payment options and refunds", ["20", "21", "22"]),
    EvalItem("How to contact support?", ["23", "24", "25"]),
    EvalItem("Contact information or phone number", ["23", "24", "25"]),
    EvalItem("Emergency or feedback contact", ["23", "24", "25"]),
    EvalItem("Check availability for a date", ["14", "15", "16"]),
    EvalItem("Pricing and discounts", ["11", "12", "13"]),
    EvalItem("Is there EV charging? Electric vehicle", ["28", "29"]),
    EvalItem("Accessibility and disabled parking", ["26", "27"]),
    EvalItem("Security cameras and surveillance", ["30"]),
]

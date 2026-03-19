"""Guard rails for filtering sensitive data"""

import re
from typing import Any, Dict, List

try:
    from transformers import pipeline

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    pipeline = None


class SensitiveDataFilter:
    """Detects and redacts SSN, card, email, phone; optional NER for names/orgs."""

    # SSN: allow ASCII hyphen, en-dash, em-dash, and optional spaces (LLMs may use Unicode)
    _SSN_PATTERN = r"\b\d{3}\s*[\-–—]\s*\d{2}\s*[\-–—]\s*\d{4}\b"

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = threshold
        self.sensitive_patterns = [
            SensitiveDataFilter._SSN_PATTERN,
            r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            r"\b\d{3}[\s\-–—]?\d{3}[\s\-–—]?\d{4}\b",  # US phone; same dash/space flexibility
        ]
        self.ner_pipeline = None
        if TRANSFORMERS_AVAILABLE and pipeline is not None:
            try:
                from transformers.utils import logging as transformers_logging

                transformers_logging.set_verbosity_error()
                self.ner_pipeline = pipeline(
                    "ner", model="dslim/bert-base-NER", aggregation_strategy="simple"
                )
            except Exception:
                pass

    # When allow_reservation_data=True we only block SSN and card (first two patterns).
    _RESERVATION_BLOCKED_PATTERN_COUNT = 2

    def contains_sensitive_data(self, text: str) -> bool:
        """Return True if text matches sensitive patterns or NER entities above threshold."""
        for pattern in self.sensitive_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        if self.ner_pipeline:
            try:
                entities = self.ner_pipeline(text)
                for entity in entities:
                    if entity.get("entity_group") in ("PER", "ORG", "MISC"):
                        if entity.get("score", 0) >= self.threshold:
                            return True
            except Exception:
                pass
        return False

    def contains_sensitive_data_reservation_query(self, text: str) -> bool:
        """True if text contains SSN or card only (for reservation flow; no email/phone)."""
        patterns = self.sensitive_patterns[: self._RESERVATION_BLOCKED_PATTERN_COUNT]
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def filter_sensitive_data(self, text: str, replacement: str = "[REDACTED]") -> str:
        """Replace sensitive spans with replacement; return filtered text."""
        if not self.contains_sensitive_data(text):
            return text
        filtered_text = text
        for pattern in self.sensitive_patterns:
            filtered_text = re.sub(pattern, replacement, filtered_text, flags=re.IGNORECASE)
        if self.ner_pipeline:
            try:
                entities = self.ner_pipeline(text)
                for entity in entities:
                    if entity.get("entity_group") in ("PER", "ORG", "MISC"):
                        if entity.get("score", 0) >= self.threshold:
                            filtered_text = filtered_text.replace(
                                entity.get("word", ""), replacement
                            )
            except Exception:
                pass
        return filtered_text

    def filter_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return documents with sensitive content in 'content' filtered or dropped."""
        filtered_docs = []
        for doc in documents:
            if "content" in doc:
                if self.contains_sensitive_data(doc["content"]):
                    continue
                doc_copy = doc.copy()
                doc_copy["content"] = self.filter_sensitive_data(doc["content"])
                filtered_docs.append(doc_copy)
            else:
                filtered_docs.append(doc)
        return filtered_docs

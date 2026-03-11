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

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = threshold
        self.sensitive_patterns = [
            r"\b\d{3}-\d{2}-\d{4}\b",
            r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            r"\b\d{3}-\d{3}-\d{4}\b",
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

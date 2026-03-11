"""Main guard rails module"""

from typing import Any, Dict, List, Optional, Tuple

from .sensitive_data_filter import SensitiveDataFilter


class GuardRails:
    """Validates queries and responses for sensitive data; filters retrieved documents."""

    def __init__(self, enabled: bool = True, threshold: float = 0.7) -> None:
        self.enabled = enabled
        self.filter = SensitiveDataFilter(threshold=threshold) if enabled else None

    def validate_query(
        self, query: str, allow_reservation_data: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """Return (True, None) if safe; (False, error_message) if sensitive data detected."""
        if not self.enabled:
            return True, None
        if allow_reservation_data:
            import re

            sensitive_patterns = [
                r"\b\d{3}-\d{2}-\d{4}\b",
                r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
            ]
            for pattern in sensitive_patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return (
                        False,
                        "Query contains potentially sensitive information. Please rephrase.",
                    )
            return True, None
        if self.filter and self.filter.contains_sensitive_data(query):
            return False, "Query contains potentially sensitive information. Please rephrase."
        return True, None

    def validate_response(self, response: str) -> Tuple[bool, str]:
        """Return (True, response) or (True, redacted_response) if sensitive data was redacted."""
        if not self.enabled:
            return True, response
        if self.filter and self.filter.contains_sensitive_data(response):
            return True, self.filter.filter_sensitive_data(response)
        return True, response

    def filter_retrieved_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter or redact sensitive content in documents before passing to LLM."""
        if not self.enabled or not self.filter:
            return documents
        return self.filter.filter_documents(documents)

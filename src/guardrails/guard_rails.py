"""Main guard rails module"""

from typing import Any, Dict, List, Optional, Tuple

from .sensitive_data_filter import SensitiveDataFilter


class GuardRails:
    def __init__(self, enabled: bool = True, threshold: float = 0.7):
        self.enabled = enabled
        self.filter = SensitiveDataFilter(threshold=threshold) if enabled else None

    def validate_query(
        self, query: str, allow_reservation_data: bool = False
    ) -> Tuple[bool, Optional[str]]:
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
        if not self.enabled:
            return True, response
        if self.filter and self.filter.contains_sensitive_data(response):
            return True, self.filter.filter_sensitive_data(response)
        return True, response

    def filter_retrieved_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.enabled or not self.filter:
            return documents
        return self.filter.filter_documents(documents)

    def is_enabled(self) -> bool:
        return self.enabled

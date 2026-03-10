"""RAG evaluation: retrieval metrics (Recall@K, Precision@K) and performance (latency)."""

from .eval_dataset import EvalItem
from .rag_evaluator import EvaluationReport, RAGEvaluator, format_report

__all__ = ["RAGEvaluator", "EvalItem", "EvaluationReport", "format_report"]

"""RAG evaluation: retrieval metrics (Recall@K, Precision@K) and performance (latency)."""
from .rag_evaluator import RAGEvaluator, EvaluationReport, format_report
from .eval_dataset import EvalItem

__all__ = ["RAGEvaluator", "EvalItem", "EvaluationReport", "format_report"]

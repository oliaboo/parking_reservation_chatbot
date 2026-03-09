"""Tests for RAG evaluation (Recall@K, Precision@K)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.evaluation.rag_evaluator import (
    RAGEvaluator,
    EvaluationReport,
    format_report,
    _recall_at_k,
    _precision_at_k,
)
from src.evaluation.eval_dataset import EvalItem, DEFAULT_EVAL_DATASET


class MockVectorStore:
    """Returns fixed doc IDs in order for any query (for testing metrics)."""
    def __init__(self, results_per_query=None):
        # results_per_query: list of list of doc IDs, one per eval item in order
        self.results_per_query = results_per_query or []

    def similarity_search(self, query: str, k: int = 5, filter=None):
        # Return next pre-set result or default [1,2,3,4,5]
        if self.results_per_query:
            ids = self.results_per_query.pop(0) if self.results_per_query else ["1", "2", "3", "4", "5"]
        else:
            ids = ["1", "2", "3", "4", "5"]
        return [{"id": i, "content": f"doc {i}", "score": 1.0} for i in ids[:k]]


def test_recall_at_k():
    assert _recall_at_k(["1", "2", "3"], ["1", "2"], k=2) == 1.0
    assert _recall_at_k(["1", "2", "3"], ["1", "2"], k=1) == 0.5
    assert _recall_at_k(["1", "2"], ["3"], k=3) == 0.0
    assert _recall_at_k([], ["1"], k=1) == 0.0


def test_precision_at_k():
    assert _precision_at_k(["1", "2", "3"], ["1", "2"], k=3) == 2 / 3
    assert _precision_at_k(["1", "2"], ["1", "2"], k=2) == 1.0
    assert _precision_at_k(["1", "2", "3"], ["9"], k=3) == 0.0


def test_evaluator_returns_report():
    # Perfect retrieval: first result is always the relevant doc for first query
    dataset = [EvalItem("test query", ["1"])]
    mock_store = MockVectorStore(results_per_query=[["1", "2", "3"]])
    evaluator = RAGEvaluator(vector_store=mock_store, eval_dataset=dataset, k_values=[1, 3])
    report = evaluator.run_retrieval_evaluation()
    assert report.num_queries == 1
    assert report.recall_at_k[1] == 1.0
    assert report.precision_at_k[1] == 1.0
    assert report.recall_at_k[3] == 1.0
    assert report.precision_at_k[3] == 1.0 / 3
    assert len(report.retrieval_latencies_ms) == 1


def test_evaluator_zero_recall():
    dataset = [EvalItem("query", ["99"])]
    mock_store = MockVectorStore(results_per_query=[["1", "2", "3"]])
    evaluator = RAGEvaluator(vector_store=mock_store, eval_dataset=dataset, k_values=[3])
    report = evaluator.run_retrieval_evaluation()
    assert report.recall_at_k[3] == 0.0
    assert report.precision_at_k[3] == 0.0


def test_format_report():
    report = EvaluationReport(
        recall_at_k={1: 0.5, 3: 0.7},
        precision_at_k={1: 0.5, 3: 0.3},
        retrieval_latency_ms=10.0,
        num_queries=2,
    )
    text = format_report(report)
    assert "Recall@1" in text
    assert "Precision@3" in text
    assert "10.00 ms" in text


def test_default_dataset_loaded():
    assert len(DEFAULT_EVAL_DATASET) >= 5
    for item in DEFAULT_EVAL_DATASET:
        assert item.query
        assert isinstance(item.relevant_doc_ids, list)
        assert all(isinstance(x, str) for x in item.relevant_doc_ids)

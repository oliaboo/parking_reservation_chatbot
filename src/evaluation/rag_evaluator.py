"""
RAG evaluation: retrieval accuracy (Recall@K, Precision@K) and performance (latency).

Additional criterion: after retrieving top-k chunks, results are filtered by similarity
score >= 0.5. Only chunks passing this threshold are used when computing Recall@K and
Precision@K. This filter is applied in run_retrieval_evaluation().
"""
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

try:
    from .eval_dataset import EvalItem, DEFAULT_EVAL_DATASET
except ImportError:
    from src.evaluation.eval_dataset import EvalItem, DEFAULT_EVAL_DATASET


@dataclass
class EvaluationReport:
    """Results of RAG evaluation."""
    recall_at_k: Dict[int, float] = field(default_factory=dict)  # K -> mean Recall@K
    precision_at_k: Dict[int, float] = field(default_factory=dict)
    retrieval_latency_ms: float = 0.0
    retrieval_latencies_ms: List[float] = field(default_factory=list)
    num_queries: int = 0
    details_per_query: List[Dict[str, Any]] = field(default_factory=list)


def _recall_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """Recall@K = |retrieved_top_k ∩ relevant| / |relevant|. If no relevant docs, return 0."""
    relevant_set = set(relevant_ids)
    if not relevant_set:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = len(relevant_set & set(top_k))
    return hits / len(relevant_set)


def _precision_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """Precision@K = |retrieved_top_k ∩ relevant| / k."""
    relevant_set = set(relevant_ids)
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = len(relevant_set & set(top_k))
    return hits / len(top_k)


class RAGEvaluator:
    """
    Evaluate RAG retrieval: Recall@K, Precision@K, and retrieval latency.
    Uses a vector store (or RAG system) and a list of EvalItems (query + relevant_doc_ids).
    Top-k retrieved chunks are filtered by similarity score >= 0.5 before computing metrics.
    """

    def __init__(
        self,
        vector_store: Any,
        eval_dataset: Optional[List[EvalItem]] = None,
        k_values: Optional[List[int]] = None,
    ):
        """
        Args:
            vector_store: Must have similarity_search(query, k) returning list of dicts with "id" key.
            eval_dataset: List of EvalItem; if None, uses DEFAULT_EVAL_DATASET.
            k_values: K values for Recall@K and Precision@K (e.g. [1, 3, 5]).
        """
        self.vector_store = vector_store
        self.eval_dataset = eval_dataset or DEFAULT_EVAL_DATASET
        self.k_values = k_values or [1, 3, 5]

    def run_retrieval_evaluation(self) -> EvaluationReport:
        """
        Run retrieval for each eval query; compute Recall@K and Precision@K and latency.
        Does not call the LLM.

        Top-k results from similarity_search are filtered: only chunks with
        similarity score >= 0.5 are kept. Recall@K and Precision@K are computed
        on this filtered list (order preserved).
        """
        report = EvaluationReport(num_queries=len(self.eval_dataset))
        max_k = max(self.k_values)
        latencies_ms: List[float] = []
        min_score_threshold = 0.5

        for item in self.eval_dataset:
            start = time.perf_counter()
            results = self.vector_store.similarity_search(item.query, k=max_k)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

            # Filter: keep only chunks with similarity score >= 0.5 (order preserved)
            retrieved_ids = [
                r.get("id", "")
                for r in results
                if r.get("id") and r.get("score", -1) >= min_score_threshold
            ]
            relevant = list(item.relevant_doc_ids)

            detail = {
                "query": item.query,
                "retrieved_ids": retrieved_ids,
                "relevant_ids": relevant,
                "latency_ms": round(elapsed_ms, 2),
            }
            for k in self.k_values:
                detail[f"recall@{k}"] = _recall_at_k(retrieved_ids, relevant, k)
                detail[f"precision@{k}"] = _precision_at_k(retrieved_ids, relevant, k)
            report.details_per_query.append(detail)

        report.retrieval_latencies_ms = latencies_ms
        report.retrieval_latency_ms = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0

        for k in self.k_values:
            report.recall_at_k[k] = sum(d[f"recall@{k}"] for d in report.details_per_query) / len(report.details_per_query)
            report.precision_at_k[k] = sum(d[f"precision@{k}"] for d in report.details_per_query) / len(report.details_per_query)

        return report

    def run_performance_test(self, num_runs: int = 5, k: int = 5) -> Dict[str, float]:
        """
        Run retrieval repeatedly to measure average latency (no accuracy).
        Returns dict with mean_ms, min_ms, max_ms.
        """
        if not self.eval_dataset:
            return {"mean_ms": 0, "min_ms": 0, "max_ms": 0}
        times_ms = []
        for _ in range(num_runs):
            q = self.eval_dataset[0].query
            start = time.perf_counter()
            self.vector_store.similarity_search(q, k=k)
            times_ms.append((time.perf_counter() - start) * 1000)
        return {
            "mean_ms": sum(times_ms) / len(times_ms),
            "min_ms": min(times_ms),
            "max_ms": max(times_ms),
        }


def format_report(report: EvaluationReport, include_per_query: bool = False) -> str:
    """Produce a human-readable evaluation report."""
    lines = [
        "=" * 60,
        "RAG EVALUATION REPORT",
        "=" * 60,
        f"Number of queries: {report.num_queries}",
        "",
        "Retrieval accuracy (mean over queries):",
    ]
    for k in sorted(report.recall_at_k.keys()):
        lines.append(f"  Recall@{k}:    {report.recall_at_k[k]:.4f}")
    for k in sorted(report.precision_at_k.keys()):
        lines.append(f"  Precision@{k}: {report.precision_at_k[k]:.4f}")
    lines.extend([
        "",
        "Performance:",
        f"  Mean retrieval latency: {report.retrieval_latency_ms:.2f} ms",
        f"  Min latency: {min(report.retrieval_latencies_ms):.2f} ms" if report.retrieval_latencies_ms else "",
        f"  Max latency: {max(report.retrieval_latencies_ms):.2f} ms" if report.retrieval_latencies_ms else "",
        "=" * 60,
    ])
    if include_per_query and report.details_per_query:
        lines.append("")
        lines.append("Per-query details (first 3):")
        for d in report.details_per_query[:3]:
            lines.append(f"  Query: {d['query'][:50]}...")
            lines.append(f"    Retrieved IDs: {d['retrieved_ids']}, Relevant: {d['relevant_ids']}")
            for k in sorted(report.recall_at_k.keys()):
                lines.append(f"    Recall@{k}={d[f'recall@{k}']:.2f}, Precision@{k}={d[f'precision@{k}']:.2f}")
    return "\n".join(lines)

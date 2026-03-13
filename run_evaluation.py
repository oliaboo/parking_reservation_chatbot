"""
Run RAG evaluation: retrieval accuracy (Recall@K, Precision@K) and performance (latency).
Uses the same vector store as the chatbot (parking_info.txt, sentence-transformers).
No LLM or DB required for retrieval-only evaluation.
"""

import argparse
import sys
from pathlib import Path

# Project root on path
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.config import settings
from src.evaluation.rag_evaluator import RAGEvaluator, format_report
from src.vector_db.vector_store import VectorStore


def main():
    parser = argparse.ArgumentParser(
        description="Run RAG evaluation (Recall@K, Precision@K, retrieval latency)."
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Write the report to evaluation_reports/FILE (e.g. -o evaluation_report.txt)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.4,
        metavar="T",
        help="Min similarity score to count a chunk (default 0.4; lower = more inclusive, higher recall)",
    )
    parser.add_argument(
        "--remove-index",
        action="store_true",
        help="Remove FAISS index files (rag_data/faiss_parking.index, faiss_parking_docs.json) after the run",
    )
    args = parser.parse_args()

    print("Loading vector store (embedding model + parking_info.txt)...")
    try:
        vector_store = VectorStore(
            embedding_model=settings.embedding_model,
            use_mock=settings.use_mock_db,
            faiss_metric=settings.faiss_metric,
        )
        # Trigger client init so chunks are embedded
        _ = vector_store.client
    except Exception as e:
        print(f"Failed to load vector store: {e}")
        print("Install: pip install sentence-transformers faiss-cpu")
        sys.exit(1)

    print("Running retrieval evaluation (Recall@K, Precision@K, latency)...")
    # Retrieve at most 5 chunks per query (k_values 1, 3, 5)
    evaluator = RAGEvaluator(
        vector_store=vector_store,
        k_values=[1, 3, 5],
        min_score_threshold=args.min_score,
    )
    report = evaluator.run_retrieval_evaluation()

    report_text = format_report(
        report,
        include_per_query=True,
        min_score_threshold=evaluator.min_score_threshold,
    )
    print(report_text)

    # Performance test (repeated runs)
    perf = evaluator.run_performance_test(num_runs=5, k=5)
    perf_text = (
        "\nPerformance test (5 runs, single query):\n"
        f"  Mean: {perf['mean_ms']:.2f} ms  Min: {perf['min_ms']:.2f} ms  Max: {perf['max_ms']:.2f} ms\n"
    )
    print(perf_text)

    if args.output:
        reports_dir = _root / "evaluation_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        out_path = reports_dir / Path(args.output).name
        # Save report with all per-query details (max_per_query=None)
        full_report_text = (
            format_report(
                report,
                include_per_query=True,
                max_per_query=None,
                min_score_threshold=evaluator.min_score_threshold,
            )
            + perf_text
        )
        out_path.write_text(full_report_text, encoding="utf-8")
        print(f"Report written to {out_path}")

    if args.remove_index:
        index_path = _root / "rag_data" / "faiss_parking.index"
        docs_path = _root / "rag_data" / "faiss_parking_docs.json"
        for p in (index_path, docs_path):
            if p.exists():
                p.unlink()
                print(f"Removed {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

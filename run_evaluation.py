"""
Run RAG evaluation: retrieval accuracy (Recall@K, Precision@K) and performance (latency).
Uses the same vector store as the chatbot (parking_info.txt, sentence-transformers).
No LLM or DB required for retrieval-only evaluation.
"""

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
    print("Loading vector store (embedding model + parking_info.txt)...")
    try:
        vector_store = VectorStore(
            embedding_model=settings.embedding_model,
            use_mock=settings.use_mock_db,
        )
        # Trigger client init so chunks are embedded
        _ = vector_store.client
    except Exception as e:
        print(f"Failed to load vector store: {e}")
        print("Install: pip install sentence-transformers faiss-cpu")
        sys.exit(1)

    print("Running retrieval evaluation (Recall@K, Precision@K, latency)...")
    evaluator = RAGEvaluator(vector_store=vector_store, k_values=[1, 3, 5])
    report = evaluator.run_retrieval_evaluation()

    print(format_report(report, include_per_query=True))

    # Performance test (repeated runs)
    print("\nPerformance test (5 runs, single query):")
    perf = evaluator.run_performance_test(num_runs=5, k=5)
    print(
        f"  Mean: {perf['mean_ms']:.2f} ms  Min: {perf['min_ms']:.2f} ms  Max: {perf['max_ms']:.2f} ms"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

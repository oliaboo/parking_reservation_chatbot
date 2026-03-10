# Evaluation reports

Reports in this folder were generated with **`run_evaluation.py`** (run from the project root).

They are produced by the evaluation logic in **`src/evaluation/`** (e.g. `rag_evaluator.py`, `eval_dataset.py`) using the RAG text and vector data in **`rag_data/`** (e.g. `parking_info.txt`, and the FAISS index built from it). Each report includes retrieval metrics (Recall@K, Precision@K), latency, and optional per-query details.

To regenerate reports, see the main [README](../README.md) and [docs/EVALUATION.md](../docs/EVALUATION.md).

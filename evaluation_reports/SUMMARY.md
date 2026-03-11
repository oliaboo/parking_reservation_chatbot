# Evaluation reports

Reports in this folder were generated with **`run_evaluation.py`** (run from the project root).

They are produced by the evaluation logic in **`src/evaluation/`** (e.g. `rag_evaluator.py`, `eval_dataset.py`) using the RAG text and vector data in **`rag_data/`** (e.g. `parking_info.txt`, and the FAISS index built from it). Each report includes retrieval metrics (Recall@K, Precision@K), latency, and optional per-query details.

To regenerate reports, see the main [README](../README.md) and [docs/EVALUATION.md](../docs/EVALUATION.md).


# Cosine vs L2 — retrieval accuracy and performance

Comparison of `evaluation_report_cosine.txt` and `evaluation_report_l2.txt` (21 queries, min score 0.4).

---

## Retrieval accuracy (mean over queries)

| Metric | Cosine | L2 | Better |
|--------|--------|-----|--------|
| **Recall@1** | 0.278 | 0.294 | L2 |
| **Recall@3** | 0.540 | 0.635 | L2 |
| **Recall@5** | 0.571 | 0.714 | L2 |
| **Precision@1** | 0.714 | 0.762 | L2 |
| **Precision@3** | 0.691 | 0.603 | Cosine |
| **Precision@5** | 0.629 | 0.484 | Cosine |

- **L2** has better recall at all K and better precision at K=1: it surfaces more relevant docs in the top results.
- **Cosine** has better precision at K=3 and K=5: among the top-3 and top-5, a larger fraction of returned docs are relevant (less noise).

So: L2 is better at **not missing** relevant chunks; cosine is slightly better at **keeping the top-K list “clean”** (precision at K=3 and K=5).

---

## Performance (latency)

| Metric | Cosine | L2 |
|--------|--------|-----|
| **Mean (over 21 queries)** | 9.15 ms | 9.90 ms |
| **Min** | 3.31 ms | 3.34 ms |
| **Max** | 31.69 ms | 44.27 ms |
| **5-run test (single query)** | Mean 3.29 ms | Mean 3.40 ms |

Latency is very similar: cosine is a bit faster on average and has a lower max in this run; the 5-run test is ~0.1 ms apart. For practical use the difference is negligible.

---

## Summary

- **Accuracy:** Prefer **L2** if you care most about recall (finding all relevant chunks). Prefer **cosine** if you care more about precision in the top-3/top-5.
- **Performance:** Effectively the same; cosine is only slightly faster in these numbers.

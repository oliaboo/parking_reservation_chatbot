# RAG Evaluation

This document describes how to run **performance testing** and **response accuracy** evaluation for the RAG system using Recall@K, Precision@K, and retrieval latency.

---

## What is evaluated

| Metric | Description |
|--------|-------------|
| **Recall@K** | Of all relevant documents for a query, what fraction appear in the top-K retrieved? Mean over eval queries. |
| **Precision@K** | Of the top-K retrieved documents, what fraction are relevant? Mean over eval queries. |
| **Retrieval latency** | Time (ms) to run one similarity search (embed query + vector search). Mean, min, max over queries or over repeated runs. |

Evaluation uses **retrieval only** (no LLM): the same vector store and embeddings as the chatbot, with a fixed set of test queries and ground-truth relevant document IDs. This avoids LLM variability and focuses on whether the right chunks from `parking_info.txt` are retrieved.

**Additional criterion:** In `run_retrieval_evaluation()`, the top-k chunks returned by similarity search are **filtered by similarity score ≥ min_score_threshold** (default **0.4**). Only chunks at or above the threshold are used when computing Recall@K and Precision@K (order is preserved). You can pass `min_score_threshold` to `RAGEvaluator` or use `--min-score` in `run_evaluation.py` to override.

---

## Quick start

From the project root (with dependencies and optionally network for the embedding model):

```bash
python run_evaluation.py
```

Output includes mean Recall@1, Recall@3, Recall@5, Precision@1/3/5, mean retrieval latency, and a short performance test (5 runs).

---

## Components

### 1. Evaluation module (`src/evaluation/`)

- **`eval_dataset.py`** — Defines `EvalItem(query, relevant_doc_ids)` and `DEFAULT_EVAL_DATASET`: list of queries with the doc IDs (from the mock Weaviate chunk order) that should be retrieved. Chunk IDs 1, 2, 3, … correspond to the order of paragraphs/sections in `parking_info.txt`.
- **`rag_evaluator.py`** — `RAGEvaluator(vector_store, eval_dataset, k_values)`:
  - `run_retrieval_evaluation()` — For each eval query, runs `vector_store.similarity_search(query, k=max_k)`, then **filters** the top-k results to those with **similarity score ≥ min_score_threshold** (default 0.4), measures latency, and computes Recall@K and Precision@K for each K in `k_values` (using the filtered list).
  - `run_performance_test(num_runs, k)` — Runs retrieval repeatedly and returns mean/min/max latency.
  - `EvaluationReport` — Holds recall_at_k, precision_at_k, retrieval_latency_ms, details_per_query.
- **`format_report(report)`** — Returns a human-readable report string.

### 2. Script `run_evaluation.py`

1. Loads the same `VectorStore` as the chatbot (embedding model + mock Weaviate with `parking_info.txt`).
2. Creates `RAGEvaluator` with default dataset and `k_values=[1, 3, 5]`.
3. Runs `run_retrieval_evaluation()` and prints the report (with optional per-query details).
4. Runs `run_performance_test(5, 5)` and prints mean/min/max latency.

No database or LLM is required; only the vector store (and thus the embedding model) is used.

**Options:**

| Option | Description |
|--------|-------------|
| `-o FILE`, `--output FILE` | Write the full report (including all per-query details) to FILE. |
| `--min-score T` | Minimum similarity score to count a chunk (default 0.4). Only chunks with score ≥ T are used for Recall@K and Precision@K. |
| `--remove-index` | After the run, delete the FAISS index files `data/faiss_parking.index` and `data/faiss_parking_docs.json`. Use this to force a fresh index on the next run (e.g. after changing `FAISS_METRIC` or `parking_info.txt`). |

---

## Metric definitions

- **Recall@K** = (number of relevant docs in top-K) / (total number of relevant docs).  
  High recall means we don’t miss relevant content.

- **Precision@K** = (number of relevant docs in top-K) / K.  
  High precision means the top-K are mostly relevant.

For each eval item, “relevant” is defined by the ground-truth `relevant_doc_ids` in the dataset. Retrieved doc IDs come from the vector store’s similarity search result (`id` field), **after filtering** to keep only chunks whose similarity `score` is ≥ min_score_threshold (default 0.4).

---

## Customizing the eval dataset

Edit `src/evaluation/eval_dataset.py`:

- Add or change entries in `DEFAULT_EVAL_DATASET`: each `EvalItem(query, relevant_doc_ids)`.
- `relevant_doc_ids` must be the string IDs of chunks (e.g. `"1"`, `"2"`, …) that the mock store assigns to `parking_info.txt` chunks in order.

To see which chunk has which ID, run the mock once and inspect the order of chunks (or add a small script that loads the mock and prints chunk IDs and a short snippet).

---

## FAISS similarity metric

The vector store uses FAISS with a configurable similarity metric (env **`FAISS_METRIC`**, default **`cosine`**):

- **`cosine`** — Normalized vectors + `IndexFlatIP` (inner product = cosine similarity). Scores in [-1, 1].
- **`l2`** — `IndexFlatL2` (squared Euclidean distance). Scores are returned as `1/(1+distance)` so higher = more similar; evaluation’s `min_score_threshold` behaves the same.

**Changing the metric requires rebuilding the index:** delete `data/faiss_parking.index` (and optionally `data/faiss_parking_docs.json`), then run the chatbot or `run_evaluation.py` so the index is rebuilt with the new metric. You can also run `python run_evaluation.py --remove-index` to delete the index files after an evaluation run, so the next run rebuilds from scratch.

---

## Tests

Unit tests for the evaluation logic (metrics and report) live in `tests/test_rag_evaluation.py`:

```bash
pytest tests/test_rag_evaluation.py -v
```

They use a mock vector store that returns fixed doc IDs, so no embedding model or network is needed.

---

## Optional: end-to-end RAG latency

The current script does **not** measure full RAG latency (retrieval + LLM). To add it you would:

1. Initialize `RAGSystem` (with vector store, LLM, guard rails, optional DB).
2. For a few queries, call `rag_system.generate_response(query)` and measure elapsed time.
3. Report mean/min/max and optionally p95.

This requires the local LLM to be available and is slower; the main evaluation focuses on retrieval accuracy and retrieval performance only.

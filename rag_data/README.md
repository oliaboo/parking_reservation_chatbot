# RAG data

This folder holds **text data** and its **vector representation** used by the RAG system. The contents here are **example data** for development and evaluation and are safe to commit.

**Production:** Do not push real RAG data (proprietary content, user data, PII) to the repo. Keep production corpora and indexes in secure storage and out of version control.

| File | Description |
|------|--------------|
| `parking_info.txt` | Source text: parking facility info (location, hours, booking, etc.). Chunked by paragraph for retrieval. |
| `faiss_parking.index` | FAISS vector index (embeddings of chunks). Rebuilt when missing or when `parking_info.txt` or `FAISS_METRIC` changes. |
| `faiss_parking_docs.json` | Doc store: id, content, metadata per chunk; used to resolve FAISS results to text. |

The SQLite database (reservations, users, prices, hours) is in `data/parking.db`.

The vector index is built from `parking_info.txt` by the chatbot or `run_evaluation.py`. To force a rebuild, delete `faiss_parking.index` (and optionally `faiss_parking_docs.json`), or run `python run_evaluation.py --remove-index`.

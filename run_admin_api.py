"""Run the admin REST API for reservation request approval.

Uses the same DB as the chatbot (data/parking.db). Set PYTHONPATH to project root, then:
  python run_admin_api.py
or:
  uvicorn src.admin_api.app:app --host 0.0.0.0 --port 8000
"""

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.admin_api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )

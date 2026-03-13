"""Configuration management"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings


def _get_project_root() -> Path:
    """Project root = first existing directory in PYTHONPATH. PYTHONPATH must be set."""
    pythonpath = os.environ.get("PYTHONPATH", "").strip()
    if not pythonpath:
        raise SystemExit(
            "PYTHONPATH must be set to the project root.\n"
            "Example: export PYTHONPATH=/path/to/parking_reservation_chatbot\n"
            "Then run: python run_chatbot_agent.py (or pytest, etc.)"
        )
    for p in pythonpath.split(os.pathsep):
        p = p.strip()
        if not p:
            continue
        path = Path(p).resolve()
        if path.is_dir():
            return path
    raise SystemExit(
        f"PYTHONPATH is set but no valid directory found: {pythonpath!r}\n"
        "Set PYTHONPATH to the project root directory (e.g. export PYTHONPATH=/path/to/parking_reservation_chatbot)."
    )


# Project root — .env and relative paths (local_models/, logs/, etc.) are resolved against this
PROJECT_ROOT = _get_project_root()
load_dotenv(PROJECT_ROOT / ".env")


def _resolve_path(value: str) -> str:
    """Resolve relative paths against project root so the app works from any cwd."""
    if not value:
        return value
    p = Path(value)
    if not p.is_absolute():
        return str(PROJECT_ROOT / p)
    return value


class Settings(BaseSettings):
    """Application settings"""

    # Model Configuration
    model_path: str = _resolve_path(
        os.getenv("MODEL_PATH", "local_models/Meta-Llama-3-8B-Instruct.Q4_0.gguf")
    )
    model_type: str = os.getenv("MODEL_TYPE", "gpt4all")
    temperature: float = float(os.getenv("TEMPERATURE", "0.7"))
    max_context_length: int = int(os.getenv("MAX_CONTEXT_LENGTH", "2048"))
    # Max tokens to generate per call (n_predict). Keep below context so prompt + output fits; 512 avoids "context full" on first call.
    max_tokens_to_generate: int = int(os.getenv("MAX_TOKENS_TO_GENERATE", "150"))

    # Vector store (FAISS over rag_data/parking_info.txt)
    use_mock_db: bool = True  # Use FAISS over parking_info.txt
    # FAISS similarity: "cosine" (IndexFlatIP + normalized) or "l2" (IndexFlatL2, Euclidean)
    faiss_metric: str = os.getenv("FAISS_METRIC", "cosine").lower()

    # Embedding Model
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    # Guard Rails Configuration
    enable_guard_rails: bool = os.getenv("ENABLE_GUARD_RAILS", "true").lower() == "true"
    sensitive_data_threshold: float = float(os.getenv("SENSITIVE_DATA_THRESHOLD", "0.7"))

    # Evaluation Configuration
    evaluation_enabled: bool = os.getenv("EVALUATION_ENABLED", "true").lower() == "true"
    metrics_k: int = int(os.getenv("METRICS_K", "5"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = _resolve_path(os.getenv("LOG_FILE", "logs/chatbot.log"))

    # Chatbot Configuration
    chatbot_name: str = os.getenv("CHATBOT_NAME", "Parking Assistant")
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "3"))

    # Admin API. chatbot uses HTTP to create/poll requests.
    admin_api_base_url: str = os.getenv("ADMIN_API_BASE_URL", "").rstrip("/")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()

"""Configuration management"""

import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables
load_dotenv()


class Settings(BaseSettings):
    """Application settings"""

    # Model Configuration
    model_path: str = os.getenv("MODEL_PATH", "local_models/Meta-Llama-3-8B-Instruct.Q4_0.gguf")
    model_type: str = os.getenv("MODEL_TYPE", "gpt4all")
    temperature: float = float(os.getenv("TEMPERATURE", "0.7"))
    max_context_length: int = int(os.getenv("MAX_CONTEXT_LENGTH", "2048"))

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
    log_file: str = os.getenv("LOG_FILE", "logs/chatbot.log")

    # Chatbot Configuration
    chatbot_name: str = os.getenv("CHATBOT_NAME", "Parking Assistant")
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "5"))

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()

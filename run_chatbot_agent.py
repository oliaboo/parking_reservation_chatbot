"""Main entry point for the parking reservation chatbot.

Set PYTHONPATH to the project root so the "src" package is found. Paths to data/,
rag_data/, and local_models/ are resolved relative to the project root.
"""

import logging
import sys
from pathlib import Path

from src.chatbot.chatbot import ParkingChatbot
from src.chatbot.llm_setup import LLMProvider
from src.chatbot.rag_system import RAGSystem
from src.chatbot.reservation_handler import ReservationHandler
from src.config import settings
from src.db.sqlite_db import get_db
from src.guardrails.guard_rails import GuardRails
from src.vector_db.vector_store import VectorStore


def _setup_step_logger():
    """Configure a simple file logger that writes execution steps to logs/chatbot.log."""
    log_path = Path(settings.log_file).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(fmt)
    logger = logging.getLogger("chatbot.run")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _suppress_hf_and_transformers_output():
    """Suppress Hugging Face / transformers progress bars and warnings during model loads."""
    try:
        from transformers.utils import logging as transformers_logging

        transformers_logging.set_verbosity_error()
        transformers_logging.disable_progress_bar()
    except Exception:
        pass
    try:
        from huggingface_hub.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
    except Exception:
        pass


def initialize_system(nickname: str, step_logger: logging.Logger):
    """Initialize all system components and set current user by nickname."""
    _suppress_hf_and_transformers_output()
    step_logger.info("Initializing vector store")
    try:
        vector_store = VectorStore(
            embedding_model=settings.embedding_model,
            use_mock=settings.use_mock_db,
            faiss_metric=settings.faiss_metric,
        )
    except ImportError as e:
        step_logger.error("Failed to initialize vector store (import): %s", e)
        print(f"Failed to initialize vector store: {e}", file=sys.stderr)
        print(
            "Please install required dependencies: pip install sentence-transformers",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        step_logger.error("Failed to initialize vector store: %s", e)
        print(f"Failed to initialize vector store: {e}", file=sys.stderr)
        sys.exit(1)
    step_logger.info("Initializing guard rails")
    guard_rails = GuardRails(
        enabled=settings.enable_guard_rails, threshold=settings.sensitive_data_threshold
    )
    try:
        llm_provider = LLMProvider(
            model_path=settings.model_path,
            temperature=settings.temperature,
            max_tokens=settings.max_context_length,
            n_predict=settings.max_tokens_to_generate,
        )
    except Exception as e:
        step_logger.error("Failed to load LLM: %s", e)
        print(f"Failed to load LLM: {e}", file=sys.stderr)
        sys.exit(1)
    step_logger.info("LLM loaded")
    db = get_db()
    step_logger.info("Initializing RAG system")
    rag_system = RAGSystem(
        vector_store=vector_store,
        llm_provider=llm_provider,
        guard_rails=guard_rails,
        k=settings.retrieval_k,
        db=db,
    )
    step_logger.info("Initializing reservation handler")
    reservation_handler = ReservationHandler(db=db)
    reservation_handler.set_nickname(nickname)
    step_logger.info("Initializing chatbot")
    chatbot = ParkingChatbot(rag_system=rag_system, reservation_handler=reservation_handler)
    step_logger.info("System ready")
    return chatbot


def main():
    """Main function to run the chatbot"""
    step_logger = _setup_step_logger()
    step_logger.info("Starting %s", settings.chatbot_name)
    number_of_symbols = 60
    db = get_db()
    step_logger.info("Waiting for nickname")
    # Ask for nickname until it exists in users table
    while True:
        nickname = input("Enter your nickname for identification: ").strip()
        if not nickname:
            print("Nickname cannot be empty.")
            continue
        if db.user_exists(nickname):
            break
        print("Nickname not found. Please try again or use a registered nickname.")
    step_logger.info("Nickname accepted: %s", nickname)
    chatbot = initialize_system(nickname, step_logger)
    step_logger.info("Session started for %s", nickname)
    print("\n" + "=" * number_of_symbols)
    print(f"Welcome to {settings.chatbot_name}, {nickname}!")
    print("I can help you with parking information and reservations.")
    print("Type 'quit' or 'exit' to end the conversation.")
    print("=" * number_of_symbols + "\n")
    conversation_history = []

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "bye"]:
                from src.mcp_reservation_logger.client_fs import stop_mcp_fs_logger

                stop_mcp_fs_logger()
                step_logger.info("Session ended (user quit)")
                print("\nThank you for using the parking reservation system. Goodbye!")
                break

            response = chatbot.chat(user_input, conversation_history)

            print(f"\n{settings.chatbot_name}: {response}\n")

            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": response})

        except KeyboardInterrupt:
            from src.mcp_reservation_logger.client_fs import stop_mcp_fs_logger

            stop_mcp_fs_logger()
            step_logger.info("Session ended (interrupted)")
            print("\n\nInterrupted by user. Goodbye!")
            break
        except Exception as e:
            step_logger.error("Error in chat loop: %s", e)
            print(f"\nI'm sorry, I encountered an error: {str(e)}\n", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()

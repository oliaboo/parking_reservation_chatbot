"""Main entry point for the parking reservation chatbot.

Set PYTHONPATH to the project root so the "src" package is found. Paths to data/,
rag_data/, local_models/, and logs/ are resolved relative to the project root.
"""

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

# Try to import loguru, fallback to standard logging
try:
    from loguru import logger  # type: ignore

    USE_LOGURU = True
except ImportError:
    import logging

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    USE_LOGURU = False


def setup_logging():
    """Setup logging configuration"""
    log_dir = Path(settings.log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    if USE_LOGURU:
        logger.remove()  # Remove default handler
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        )
        logger.add(
            settings.log_file,
            level=settings.log_level,
            rotation="10 MB",
            retention="7 days",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        )
    else:
        # Use standard logging
        file_handler = logging.FileHandler(settings.log_file)
        file_handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)


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


def initialize_system(nickname: str):
    """Initialize all system components and set current user by nickname."""
    _suppress_hf_and_transformers_output()
    logger.info("Initializing parking reservation chatbot...")
    try:
        vector_store = VectorStore(
            embedding_model=settings.embedding_model,
            use_mock=settings.use_mock_db,
            faiss_metric=settings.faiss_metric,
        )
    except ImportError as e:
        logger.error(f"Failed to initialize vector store: {e}")
        logger.error("Please install required dependencies: pip install sentence-transformers")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to initialize vector store: {e}")
        sys.exit(1)
    logger.info("Initializing guard rails...")
    guard_rails = GuardRails(
        enabled=settings.enable_guard_rails, threshold=settings.sensitive_data_threshold
    )
    logger.info(f"Loading LLM from {settings.model_path}...")
    try:
        llm_provider = LLMProvider(
            model_path=settings.model_path,
            temperature=settings.temperature,
            max_tokens=settings.max_context_length,
            n_predict=settings.max_tokens_to_generate,
        )
        logger.info("LLM loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load LLM: {e}")
        sys.exit(1)
    db = get_db()
    logger.info("Initializing RAG system...")
    rag_system = RAGSystem(
        vector_store=vector_store,
        llm_provider=llm_provider,
        guard_rails=guard_rails,
        k=settings.retrieval_k,
        db=db,
    )
    logger.info("Initializing reservation handler...")
    reservation_handler = ReservationHandler(db=db)
    reservation_handler.set_nickname(nickname)
    logger.info("Initializing chatbot...")
    chatbot = ParkingChatbot(rag_system=rag_system, reservation_handler=reservation_handler)
    logger.info("System initialization complete!")
    return chatbot


def main():
    """Main function to run the chatbot"""
    setup_logging()
    number_of_symbols = 60
    logger.info("=" * number_of_symbols)
    logger.info(f"Starting {settings.chatbot_name}")
    logger.info("=" * number_of_symbols)
    db = get_db()
    # Ask for nickname until it exists in users table
    while True:
        nickname = input("Enter your nickname for identification: ").strip()
        if not nickname:
            print("Nickname cannot be empty.")
            continue
        if db.user_exists(nickname):
            break
        print("Nickname not found. Please try again or use a registered nickname.")
    chatbot = initialize_system(nickname)
    print("\n" + "=" * number_of_symbols)
    print(f"Welcome to {settings.chatbot_name}, {nickname}!")
    print("I can help you with parking information and reservations.")
    print("Type 'quit' or 'exit' to end the conversation.")
    print("=" * number_of_symbols + "\n")
    conversation_history = []

    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # Check for exit commands
            if user_input.lower() in ["quit", "exit", "bye"]:
                from src.mcp_reservation_logger.client_fs import stop_mcp_fs_logger

                stop_mcp_fs_logger()
                print("\nThank you for using the parking reservation system. Goodbye!")
                break

            # Get response from chatbot
            response = chatbot.chat(user_input, conversation_history)

            # Display response
            print(f"\n{settings.chatbot_name}: {response}\n")

            # Update conversation history
            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": response})

        except KeyboardInterrupt:
            try:
                from src.mcp_reservation_logger.client_fs import stop_mcp_fs_logger

                stop_mcp_fs_logger()
            except Exception:
                pass
            print("\n\nInterrupted by user. Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error in chat loop: {e}")
            print(f"\nI'm sorry, I encountered an error: {str(e)}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()

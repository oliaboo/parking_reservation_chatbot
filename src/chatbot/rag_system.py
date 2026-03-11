"""RAG system implementation using LangChain"""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import PromptTemplate

from ..guardrails.guard_rails import GuardRails
from ..vector_db.vector_store import VectorStore
from .llm_setup import LLMProvider

if TYPE_CHECKING:
    from ..db.sqlite_db import SQLiteDB


class RAGSystem:
    """RAG pipeline: retrieve docs, dynamic DB context, LLM answer, guardrails."""

    def __init__(
        self,
        vector_store: VectorStore,
        llm_provider: LLMProvider,
        guard_rails: GuardRails,
        k: int = 5,
        db: Optional["SQLiteDB"] = None,
    ):
        """Build RAG system with vector store, LLM, guardrails, and optional DB for dynamic context."""
        self.vector_store = vector_store
        self.llm_provider = llm_provider
        self.guard_rails = guard_rails
        self.k = k
        self.db = db
        self.prompt_template = PromptTemplate(
            input_variables=["context", "question"],
            template="""You are a helpful parking reservation assistant. Use the following context to answer the user's question.

Rules: Give only the direct answer to the user. Do not describe what the user asked, do not show your reasoning steps, and do not add phrases like "The user wants to know..." or "Please let me know if I can help." If the context doesn't contain enough information, say so briefly.

Context:
{context}

Question: {question}

Answer:""",
        )
        self.llm = llm_provider.get_llm()

    def retrieve_context(
        self, query: str, allow_reservation_data: bool = False
    ) -> List[Dict[str, Any]]:
        """Validate query, run similarity search, filter docs; raise ValueError if query unsafe."""
        is_safe, error_msg = self.guard_rails.validate_query(
            query, allow_reservation_data=allow_reservation_data
        )
        if not is_safe:
            raise ValueError(error_msg)
        documents = self.vector_store.similarity_search(query, k=self.k)
        return self.guard_rails.filter_retrieved_documents(documents)

    def _get_dynamic_context(self) -> str:
        """Get current prices, working hours, and availability from SQLite to include in RAG context."""
        if not self.db:
            return ""
        parts = []
        try:
            today = date.today()
            parts.append(f"Today's date: {today.isoformat()}.")
            availability_lines = []
            for i in range(7):
                d = (today + timedelta(days=i)).isoformat()
                free = self.db.get_free_spaces(d)
                if free is not None:
                    label = "today" if i == 0 else ("tomorrow" if i == 1 else d)
                    availability_lines.append(f"  - {label}: {free} spaces available")
            if availability_lines:
                parts.append("Available parking spaces (from database):\n" + "\n".join(availability_lines))
            prices = self.db.get_prices()
            if prices:
                lines = []
                for row in prices:
                    type_name, rate, unit = row
                    label = type_name.replace("_", " ").title()
                    lines.append(f"  - {label}: ${rate:.2f} per {unit}")
                parts.append("Current prices (from database):\n" + "\n".join(lines))
            hours = self.db.get_working_hours()
            if hours:
                lines = [f"  - {row[3]}: {row[1]}–{row[2]}" for row in hours]
                parts.append("Working hours (from database):\n" + "\n".join(lines))
        except Exception:
            pass
        return "\n\n".join(parts) if parts else ""

    def _format_conversation_for_prompt(self, messages: List[Any]) -> str:
        """Format last N messages as 'User: ... Assistant: ...' for the prompt."""
        lines = []
        for msg in messages:
            if hasattr(msg, "content"):
                role = "User" if isinstance(msg, HumanMessage) else "Assistant"
                lines.append(f"{role}: {msg.content}")
            elif isinstance(msg, dict):
                label = "User" if msg.get("role") == "user" else "Assistant"
                lines.append(f"{label}: {msg.get('content', '')}")
            else:
                lines.append(str(msg))
        return "\n".join(lines) if lines else ""

    def generate_response(
        self, query: str, conversation_history: Optional[List[Any]] = None
    ) -> str:
        """Retrieve context, build prompt (with optional recent conversation), run LLM, validate response."""
        documents = self.retrieve_context(query)
        dynamic = self._get_dynamic_context()
        if not documents and not dynamic:
            return "I'm sorry, I couldn't find relevant information to answer your question."
        langchain_docs = [
            Document(page_content=doc["content"], metadata=doc.get("metadata", {}))
            for doc in documents
        ]
        context_text = "\n\n".join([doc.page_content for doc in langchain_docs])
        if dynamic:
            context_text = (context_text + "\n\n" + dynamic) if context_text else dynamic
            langchain_docs = langchain_docs + [Document(page_content=dynamic, metadata={})]
        if conversation_history:
            recent = self._format_conversation_for_prompt(conversation_history)
            context_text = (
                "Recent conversation (for context):\n" + recent + "\n\n" + context_text
            )
        formatted_prompt = self.prompt_template.format(context=context_text, question=query)
        result = self.llm.invoke(formatted_prompt)
        result = result.content if hasattr(result, "content") else result
        _, filtered_response = self.guard_rails.validate_response(result)
        return filtered_response

    def get_context_string(self, query: str) -> str:
        """Return concatenated relevant context for the query (no LLM)."""
        return self.vector_store.get_relevant_context(query, k=self.k)

    INTENT_PROMPT = """You are a parking assistant. Classify the user's intent into exactly one of: reserve, show_reservations, general.

- reserve: the user wants to make or book a new parking reservation.
- show_reservations: the user wants to see, list, or view their existing reservations.
- general: any other question, statement, or request (e.g. opening hours, prices, how to book, general info).

User message: {user_input}

Reply with only one word: reserve, show_reservations, or general."""

    def classify_intent(self, user_input: str) -> str:
        """Use LLM to classify user intent as reserve, show_reservations, or general."""
        prompt = self.INTENT_PROMPT.format(user_input=user_input)
        llm = self.llm
        result = llm.invoke(prompt)
        text = (result.content if hasattr(result, "content") else str(result)).strip().lower()
        for word in text.replace("\n", " ").split():
            if word in ("reserve", "show_reservations", "general"):
                return word
        if "show_reservation" in text:
            return "show_reservations"
        if "reserve" in text:
            return "reserve"
        return "general"

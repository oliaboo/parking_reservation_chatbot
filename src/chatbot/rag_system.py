"""RAG system implementation using LangChain"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate

try:
    from langchain.chains.question_answering import load_qa_chain

    LOAD_QA_CHAIN_AVAILABLE = True
except ImportError:
    try:
        from langchain.chains import load_qa_chain

        LOAD_QA_CHAIN_AVAILABLE = True
    except ImportError:
        LOAD_QA_CHAIN_AVAILABLE = False
        load_qa_chain = None

from ..guardrails.guard_rails import GuardRails
from ..vector_db.vector_store import VectorStore
from .llm_setup import LLMProvider

if TYPE_CHECKING:
    from ..db.sqlite_db import SQLiteDB


class RAGSystem:
    def __init__(
        self,
        vector_store: VectorStore,
        llm_provider: LLMProvider,
        guard_rails: GuardRails,
        k: int = 5,
        db: Optional["SQLiteDB"] = None,
    ):
        self.vector_store = vector_store
        self.llm_provider = llm_provider
        self.guard_rails = guard_rails
        self.k = k
        self.db = db
        self.prompt_template = PromptTemplate(
            input_variables=["context", "question"],
            template="""You are a helpful parking reservation assistant. Use the following context to answer the user's question.
If the context doesn't contain enough information, politely say so.

Context:
{context}

Question: {question}

Answer:""",
        )
        if LOAD_QA_CHAIN_AVAILABLE and load_qa_chain is not None:
            try:
                self.qa_chain = load_qa_chain(
                    llm=llm_provider.get_llm(), chain_type="stuff", prompt=self.prompt_template
                )
                self._use_llm_chain = False
            except Exception:
                self._use_llm_chain = True
        else:
            self._use_llm_chain = True

        if self._use_llm_chain:
            try:
                from langchain.chains import LLMChain
            except ImportError:
                try:
                    from langchain.chains.llm import LLMChain
                except ImportError:
                    self._use_simple_chain = True
                    self.llm = llm_provider.get_llm()
                    return
            if not hasattr(self, "_use_simple_chain"):
                self.qa_chain = LLMChain(llm=llm_provider.get_llm(), prompt=self.prompt_template)

    def retrieve_context(
        self, query: str, allow_reservation_data: bool = False
    ) -> List[Dict[str, Any]]:
        is_safe, error_msg = self.guard_rails.validate_query(
            query, allow_reservation_data=allow_reservation_data
        )
        if not is_safe:
            raise ValueError(error_msg)
        documents = self.vector_store.similarity_search(query, k=self.k)
        return self.guard_rails.filter_retrieved_documents(documents)

    def _get_dynamic_context(self) -> str:
        """Get current prices and working hours from SQLite to include in RAG context."""
        if not self.db:
            return ""
        parts = []
        try:
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

    def generate_response(self, query: str) -> str:
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
        if hasattr(self, "_use_simple_chain") and self._use_simple_chain:
            formatted_prompt = self.prompt_template.format(context=context_text, question=query)
            result = self.llm.invoke(formatted_prompt)
            result = result.content if hasattr(result, "content") else result
        elif hasattr(self, "_use_llm_chain") and self._use_llm_chain:
            result = self.qa_chain.run(context=context_text, question=query)
        else:
            result = self.qa_chain.run(input_documents=langchain_docs, question=query)
        _, filtered_response = self.guard_rails.validate_response(result)
        return filtered_response

    def get_context_string(self, query: str) -> str:
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
        llm = getattr(self, "llm", None) or self.llm_provider.get_llm()
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

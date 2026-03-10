"""Main chatbot implementation using LangGraph"""

import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph

from .rag_system import RAGSystem
from .reservation_handler import ReservationHandler


class ParkingChatbot:
    def __init__(self, rag_system: RAGSystem, reservation_handler: ReservationHandler):
        self.rag_system = rag_system
        self.reservation_handler = reservation_handler
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(Dict)
        workflow.add_node("handle_general_query", self._handle_general_query)
        workflow.set_entry_point("handle_general_query")
        workflow.add_edge("handle_general_query", END)
        return workflow.compile()

    def _looks_like_date(self, text: str) -> bool:
        """True if input looks like a single date (YYYY-MM-DD) or a date range."""
        t = text.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}\s*$", t):
            return True
        if re.search(r"\d{4}-\d{2}-\d{2}\s*[-–to]+\s*\d{4}-\d{2}-\d{2}", t, re.IGNORECASE):
            return True
        # MM/DD/YYYY or DD/MM/YYYY
        if re.match(r"^\d{1,2}/\d{1,2}/\d{4}\s*$", t):
            return True
        return False

    def _answer_with_rag(self, state: Dict[str, Any], messages: List, user_input: str) -> Dict[str, Any]:
        """Produce RAG response, append AIMessage, return state."""
        try:
            response = self.rag_system.generate_response(user_input)
        except ValueError as e:
            response = (
                str(e)
                if "sensitive" not in str(e).lower()
                else "For reservations say 'I want to make a reservation' or 'book a parking space'."
            )
        except Exception as e:
            response = f"I apologize, but I encountered an error: {str(e)}"
        messages.append(AIMessage(content=response))
        state["messages"] = messages
        return state

    def _handle_general_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state
        last_message = messages[-1]
        user_input = last_message.content if hasattr(last_message, "content") else str(last_message)

        # If we're already collecting a reservation, allow other actions unless they're giving a date
        if self.reservation_handler.get_current_reservation() is not None:
            if self._looks_like_date(user_input):
                return self._handle_reservation(state)
            intent = self.rag_system.classify_intent(user_input)
            if intent == "show_reservations":
                self.reset_conversation()
                return self._handle_show_reservations(state)
            if intent == "general":
                self.reset_conversation()
                return self._answer_with_rag(state, messages, user_input)
            else:
                # intent == "reserve" or unclear: treat as reservation input
                return self._handle_reservation(state)

        # Use LLM to classify intent: reserve, show_reservations, or general
        intent = self.rag_system.classify_intent(user_input)

        if intent == "reserve":
            return self._handle_reservation(state)
        if intent == "show_reservations":
            return self._handle_show_reservations(state)

        # General question/statement: answer using RAG (LLM with context)
        return self._answer_with_rag(state, messages, user_input)

    def _handle_show_reservations(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        dates = self.reservation_handler.get_active_reservations()
        response = (
            "Your active reservations:\n" + "\n".join(f"- {d}" for d in dates)
            if dates
            else "You have no active reservations."
        )
        messages.append(AIMessage(content=response))
        state["messages"] = messages
        return state

    def _handle_reservation(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state
        last_message = messages[-1]
        user_input = last_message.content if hasattr(last_message, "content") else str(last_message)
        is_safe, error_msg = self.rag_system.guard_rails.validate_query(
            user_input, allow_reservation_data=True
        )
        if not is_safe:
            messages.append(
                AIMessage(
                    content=error_msg or "Please provide only your preferred date (YYYY-MM-DD)."
                )
            )
            state["messages"] = messages
            return state
        if not self.reservation_handler.get_current_reservation():
            self.reservation_handler.start_reservation()
            response = f"I'll help you make a reservation. {self.reservation_handler.get_next_field_prompt()}"
        else:
            _, response = self.reservation_handler.process_user_input(user_input)
        messages.append(AIMessage(content=response))
        state["messages"] = messages
        return state

    def chat(self, user_input: str, conversation_history: Optional[List] = None) -> str:
        messages = conversation_history or []
        messages.append(HumanMessage(content=user_input))
        result = self.graph.invoke({"messages": messages})
        if result.get("messages"):
            last_message = result["messages"][-1]
            if hasattr(last_message, "content"):
                return last_message.content
        return "I'm sorry, I couldn't generate a response."

    def reset_conversation(self):
        self.reservation_handler.current_reservation = None

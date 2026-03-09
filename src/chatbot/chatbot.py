"""Main chatbot implementation using LangGraph"""
from typing import Dict, Any, Optional, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from .rag_system import RAGSystem
from .reservation_handler import ReservationHandler, ReservationState


class ParkingChatbot:
    def __init__(self, rag_system: RAGSystem, reservation_handler: ReservationHandler):
        self.rag_system = rag_system
        self.reservation_handler = reservation_handler
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(Dict)
        workflow.add_node("classify_intent", self._classify_intent)
        workflow.add_node("handle_general_query", self._handle_general_query)
        workflow.add_node("handle_reservation", self._handle_reservation)
        workflow.add_node("handle_show_reservations", self._handle_show_reservations)
        workflow.set_entry_point("classify_intent")
        workflow.add_conditional_edges(
            "classify_intent",
            self._route_intent,
            {"general": "handle_general_query", "reservation": "handle_reservation", "show_reservations": "handle_show_reservations"},
        )
        workflow.add_edge("handle_general_query", END)
        workflow.add_edge("handle_reservation", END)
        workflow.add_edge("handle_show_reservations", END)
        return workflow.compile()

    def _classify_intent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state
        last_message = messages[-1]
        user_input = last_message.content if hasattr(last_message, "content") else str(last_message)
        user_input_lower = user_input.lower()
        show_keywords = ["show my reservations", "my reservations", "active reservations", "list my reservations", "show reservations"]
        if any(phrase in user_input_lower for phrase in show_keywords):
            state["intent"] = "show_reservations"
            return state
        reservation_keywords = ["reserve", "reservation", "book", "booking", "parking spot", "parking space", "date", "preferred date"]
        state["intent"] = "reservation" if any(k in user_input_lower for k in reservation_keywords) else "general"
        return state

    def _route_intent(self, state: Dict[str, Any]) -> str:
        return state.get("intent", "general")

    def _handle_general_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state
        last_message = messages[-1]
        user_input = last_message.content if hasattr(last_message, "content") else str(last_message)
        # If we're already collecting a reservation (e.g. waiting for date), treat this message as reservation input
        if self.reservation_handler.get_current_reservation() is not None:
            return self._handle_reservation(state)
        if any(k in user_input.lower() for k in ["reserve", "reservation", "book", "booking", "name", "surname", "car number", "license plate"]):
            return self._handle_reservation(state)
        try:
            response = self.rag_system.generate_response(user_input)
        except ValueError as e:
            response = str(e) if "sensitive" not in str(e).lower() else "For reservations say 'I want to make a reservation' or 'book a parking space'."
        except Exception as e:
            response = f"I apologize, but I encountered an error: {str(e)}"
        messages.append(AIMessage(content=response))
        state["messages"] = messages
        return state

    def _handle_show_reservations(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        dates = self.reservation_handler.get_active_reservations()
        response = "Your active reservations:\n" + "\n".join(f"- {d}" for d in dates) if dates else "You have no active reservations."
        messages.append(AIMessage(content=response))
        state["messages"] = messages
        return state

    def _handle_reservation(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state
        last_message = messages[-1]
        user_input = last_message.content if hasattr(last_message, "content") else str(last_message)
        is_safe, error_msg = self.rag_system.guard_rails.validate_query(user_input, allow_reservation_data=True)
        if not is_safe:
            messages.append(AIMessage(content=error_msg or "Please provide only your preferred date (YYYY-MM-DD)."))
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

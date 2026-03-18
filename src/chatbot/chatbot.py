"""Main chatbot implementation using LangGraph.

Orchestration: user interaction (RAG + chatbot) → administrator approval (wait) → data recording (MCP + DB).
"""

import re
import time
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph, add_messages

from .rag_system import RAGSystem
from .reservation_handler import ReservationHandler


class ChatState(TypedDict, total=False):
    """Graph state: messages with append reducer; pipeline fields for reservation flow."""

    messages: Annotated[list, add_messages]
    reservation_request_id: Optional[str]
    approval_result: Optional[str]


class ParkingChatbot:
    """LangGraph-based chatbot: user interaction, wait for admin approval, record data (MCP + DB)."""

    def __init__(self, rag_system: RAGSystem, reservation_handler: ReservationHandler):
        """Build chatbot with given RAG system and reservation handler."""
        self.rag_system = rag_system
        self.reservation_handler = reservation_handler
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(ChatState)
        # Node 1: user interaction (RAG context + chatbot; may escalate to admin)
        workflow.add_node("user_interaction", self._node_user_interaction)
        # Node 2: administrator approval (human-in-the-loop; we wait for API status)
        workflow.add_node("wait_for_approval", self._node_wait_for_approval)
        # Node 3: data recording (MCP + DB after confirmation)
        workflow.add_node("record_data", self._node_record_data)

        workflow.set_entry_point("user_interaction")
        workflow.add_conditional_edges(
            "user_interaction",
            self._route_after_user_interaction,
            {"wait_for_approval": "wait_for_approval", "end": END},
        )
        workflow.add_conditional_edges(
            "wait_for_approval",
            self._route_after_wait_for_approval,
            {"record_data": "record_data", "end": END},
        )
        workflow.add_edge("record_data", END)

        return workflow.compile()

    def _route_after_user_interaction(
        self, state: Dict[str, Any]
    ) -> Literal["wait_for_approval", "end"]:
        """If we escalated to admin (pending request), go to wait_for_approval; else end."""
        if state.get("reservation_request_id"):
            return "wait_for_approval"
        return "end"

    def _route_after_wait_for_approval(
        self, state: Dict[str, Any]
    ) -> Literal["record_data", "end"]:
        """If approved, go to record_data; else end."""
        if state.get("approval_result") == "approved":
            return "record_data"
        return "end"

    def _looks_like_date(self, text: str) -> bool:
        """True if input looks like a single date (YYYY-MM-DD) or a date range."""
        t = text.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}\s*$", t):
            return True
        if re.search(r"\d{4}-\d{2}-\d{2}\s*[-–to]+\s*\d{4}-\d{2}-\d{2}", t, re.IGNORECASE):
            return True
        if re.match(r"^\d{1,2}/\d{1,2}/\d{4}\s*$", t):
            return True
        return False

    def _answer_with_rag(
        self, state: Dict[str, Any], messages: List, user_input: str
    ) -> Dict[str, Any]:
        """Produce RAG response, append AIMessage, return state."""
        recent = messages[:-1][-5:]
        try:
            response = self.rag_system.generate_response(
                user_input, conversation_history=recent if recent else None
            )
        except ValueError as e:
            response = str(e)
        except Exception as e:
            response = f"I apologize, but I encountered an error: {str(e)}"
        messages.append(AIMessage(content=response))
        return {"messages": messages}

    def _node_user_interaction(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Node: user interaction (RAG + chatbot context). Escalates reservation to admin by setting reservation_request_id."""
        messages = state.get("messages", [])
        if not messages:
            return {}
        last_message = messages[-1]
        user_input = last_message.content if hasattr(last_message, "content") else str(last_message)

        is_safe, error_msg = self.rag_system.guard_rails.validate_query(
            user_input, allow_reservation_data=False
        )
        if not is_safe:
            messages.append(
                AIMessage(
                    content=error_msg
                    or "Query contains potentially sensitive information. Please rephrase."
                )
            )
            return {"messages": messages}

        if self.reservation_handler.get_current_reservation() is not None:
            if self._looks_like_date(user_input):
                return self._do_reservation_step(state, messages, user_input)
            intent = self.rag_system.classify_intent(user_input)
            if intent == "show_reservations":
                self.reset_conversation()
                return {"messages": self._show_reservations_messages(messages)}
            if intent == "general":
                self.reset_conversation()
                return self._answer_with_rag(state, messages, user_input)
            return self._do_reservation_step(state, messages, user_input)

        intent = self.rag_system.classify_intent(user_input)
        if intent == "reserve":
            return self._do_reservation_step(state, messages, user_input)
        if intent == "show_reservations":
            return {"messages": self._show_reservations_messages(messages)}
        return self._answer_with_rag(state, messages, user_input)

    def _show_reservations_messages(self, messages: List) -> List:
        dates = self.reservation_handler.get_active_reservations()
        response = (
            "Your active reservations:\n" + "\n".join(f"- {d}" for d in dates)
            if dates
            else "You have no active reservations."
        )
        out = list(messages)
        out.append(AIMessage(content=response))
        return out

    def _do_reservation_step(
        self, state: Dict[str, Any], messages: List, user_input: str
    ) -> Dict[str, Any]:
        """Handle one reservation step; if pending_approval, set reservation_request_id and return (no polling here)."""
        is_safe, error_msg = self.rag_system.guard_rails.validate_query(
            user_input, allow_reservation_data=True
        )
        if not is_safe:
            out = list(messages)
            out.append(
                AIMessage(
                    content=error_msg or "Please provide only your preferred date (YYYY-MM-DD)."
                )
            )
            return {"messages": out}
        if not self.reservation_handler.get_current_reservation():
            self.reservation_handler.start_reservation()
            response = f"I'll help you make a reservation. {self.reservation_handler.get_next_field_prompt()}"
            out = list(messages)
            out.append(AIMessage(content=response))
            return {"messages": out}
        result = self.reservation_handler.process_user_input(user_input)
        _, response = result[0], result[1]
        pending_request_id = (
            result[2] if len(result) == 3 and result[1] == "pending_approval" else None
        )
        out = list(messages)
        if pending_request_id:
            out.append(
                AIMessage(content="Request sent to the administrator. Waiting for approval...")
            )
            return {"messages": out, "reservation_request_id": pending_request_id}
        out.append(AIMessage(content=response))
        return {"messages": out}

    def _node_wait_for_approval(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Node: administrator approval (human-in-the-loop). Poll API until approved/rejected/timeout."""
        from ..admin_api.client import AdminAPIUnavailableError, get_request_status

        request_id = state.get("reservation_request_id")
        messages = list(state.get("messages", []))
        if not request_id:
            return {"approval_result": "timeout", "messages": messages}

        poll_interval = 2
        timeout_sec = 300
        start = time.monotonic()
        while (time.monotonic() - start) < timeout_sec:
            try:
                status = get_request_status(request_id)
            except AdminAPIUnavailableError as e:
                messages.append(AIMessage(content=f"Could not check request status: {e}"))
                return {"messages": messages, "approval_result": "error"}
            if status == "approved":
                return {"messages": messages, "approval_result": "approved"}
            if status == "rejected":
                messages.append(AIMessage(content="The administrator declined your request."))
                return {"messages": messages, "approval_result": "rejected"}
            time.sleep(poll_interval)
        messages.append(
            AIMessage(content="No response from administrator in time. Please try again later.")
        )
        return {"messages": messages, "approval_result": "timeout"}

    def _node_record_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Node: data recording after confirmation (apply reservation + MCP log)."""
        from ..admin_api.client import get_pending_request_details

        request_id = state.get("reservation_request_id")
        messages = list(state.get("messages", []))
        if not request_id:
            return {"messages": messages}

        ok, msg = self.reservation_handler.apply_approved_request(request_id)
        messages.append(AIMessage(content=msg))

        # MCP: log approval to CSV (name, car_number, reservation_period, approval_time)
        details = get_pending_request_details(request_id)
        if details:
            nickname, dates = details
            car_number = self.reservation_handler.db.get_plates_by_nickname(nickname) or ""
            reservation_period = ", ".join(dates) if dates else ""
            try:
                from src.mcp_reservation_logger.client_fs import log_reservation_action_via_fs_mcp

                log_reservation_action_via_fs_mcp(nickname, car_number, reservation_period)
            except Exception:
                pass  # best-effort; user already got reservation confirmation

        return {
            "messages": messages,
            "reservation_request_id": None,
            "approval_result": None,
        }

    def chat(self, user_input: str, conversation_history: Optional[List] = None) -> str:
        """Process user message and return the assistant reply (optionally with history)."""
        messages = conversation_history or []
        messages.append(HumanMessage(content=user_input))
        result = self.graph.invoke({"messages": messages})
        if result.get("messages"):
            last_message = result["messages"][-1]
            if hasattr(last_message, "content"):
                return last_message.content
        return "I'm sorry, I couldn't generate a response."

    def reset_conversation(self) -> None:
        """Clear any in-progress reservation state."""
        self.reservation_handler.current_reservation = None

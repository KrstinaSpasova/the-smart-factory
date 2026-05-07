"""
Memory Manager — thin wrapper around memory_tools.

Responsibility: persist approved decisions to SQLite and retrieve context
for the Orchestrator's system prompt.

This is intentionally plain functions (no LangChain agent) — at MVP the
Orchestrator calls these directly rather than routing through another agent.
"""

from app.tools.memory_tools import (
    save_decision as _save,
    load_past_decisions as _load,
    get_session_context as _get_context,
)


def save_decision(
    ipc_id: str,
    action: str,
    rationale: str,
    status: str = "approved",
    operator_note: str | None = None,
) -> str:
    """Persist an operator-approved decision to SQLite. Only called after HITL approval."""
    row_id = _save(ipc_id, action, rationale, status, operator_note)
    return f"Decision #{row_id} for {ipc_id} saved: {action} ({status})"


def load_past_decisions(ipc_id: str | None = None) -> list[dict]:
    """Retrieve past decisions from SQLite, optionally filtered by IPC."""
    return _load(ipc_id)


def get_session_context() -> str:
    """Plain-text summary of the last 10 decisions for injection into the Orchestrator system prompt."""
    return _get_context()

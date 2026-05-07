"""
Memory Manager — thin wrapper around M's memory_tools.

Responsibility: persist approved decisions to SQLite and retrieve context
for the Orchestrator's system prompt.

This is intentionally plain functions (no LangChain agent) — at MVP the
Orchestrator calls these directly rather than routing through another agent.
"""

# --- Hour 2 wiring point ---
# When M's memory_tools module is available after rebase, uncomment:
#
# from backend.app.tools.memory_tools import (
#     save_decision as _save,
#     load_past_decisions as _load,
#     get_session_context as _get_context,
# )


def save_decision(
    ipc_id: str,
    action: str,
    rationale: str,
    status: str = "approved",
    operator_note: str | None = None,
) -> str:
    """
    Persist an operator-approved decision to SQLite.
    Only called by the Orchestrator after HITL approval.
    Returns a confirmation string shown to the operator.
    """
    # Hour 2: replace stub with _save(ipc_id, action, rationale, status, operator_note)
    return f"[stub] Decision for {ipc_id} saved: {action} ({status})"


def load_past_decisions(ipc_id: str | None = None) -> list[dict]:
    """
    Retrieve past decisions from SQLite.
    Pass ipc_id to filter, or None to get all recent decisions.
    """
    # Hour 2: replace stub with return _load(ipc_id)
    return []


def get_session_context() -> str:
    """
    Returns a plain-text summary of the last 10 decisions.
    Injected into the Orchestrator system prompt at session start
    so the agent is aware of recent operator history.
    """
    # Hour 2: replace stub with return _get_context()
    return "No past decisions on record."

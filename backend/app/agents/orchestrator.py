import os
from langchain_openai import AzureChatOpenAI
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langfuse.langchain import CallbackHandler
from backend.app.agents.memory_manager import get_session_context

SYSTEM_PROMPT = (
    "You are the Smart Factory Operations Center assistant. "
    "You help operators manage their IPC (Industrial PC) fleet.\n\n"
    "CRITICAL HITL RULES — never break these:\n"
    "1. Never save a decision or take any write action without first asking the operator: "
    "'Do you approve this action? (yes/no)'\n"
    "2. Only call save_decision AFTER the operator replies with yes / approve / confirmed.\n"
    "3. You are read-only until the operator explicitly approves.\n"
    "4. Always explain your reasoning and recommendation before asking for approval.\n\n"
    "When analysing the fleet, summarise findings clearly, then ask for approval "
    "before recommending any hardware change."
)

# MemorySaver persists conversation history per thread_id (session_id) in memory
_checkpointer = MemorySaver()


def _get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "group1-gpt-4.1"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        temperature=0,
    )


def _build_tools() -> list:
    # --- Hour 2 wiring point ---
    # When M's modules are merged to master and you rebase, replace this block:
    #
    # from backend.app.tools.sensor_tools import (
    #     compute_utilization_stats, get_fleet_summary, get_ipc_history
    # )
    # from backend.app.tools.classifier_tools import classify_ipc, flag_anomalies
    # from backend.app.tools.memory_tools import (
    #     load_past_decisions, save_decision, get_session_context
    # )
    # from langchain_core.tools import tool
    # return [
    #     tool(compute_utilization_stats),
    #     tool(classify_ipc),
    #     tool(get_fleet_summary),
    #     tool(load_past_decisions),
    #     tool(save_decision),
    # ]
    return []


def orchestrator_invoke(message: str, session_id: str = "default") -> dict:
    """
    Public interface — this is what main.py calls.
    Returns {"reply": str, "session_id": str, "trace_id": str | None}.
    """
    context = get_session_context()
    system = SYSTEM_PROMPT + f"\n\nPast operator decisions for context:\n{context}"

    agent = create_agent(
        model=_get_llm(),
        tools=_build_tools(),
        system_prompt=system,
        checkpointer=_checkpointer,
    )

    langfuse_handler = CallbackHandler()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config={
            "configurable": {"thread_id": session_id},
            "callbacks": [langfuse_handler],
        },
    )

    reply = result["messages"][-1].content
    return {
        "reply": reply,
        "session_id": session_id,
        "trace_id": langfuse_handler.last_trace_id,
    }

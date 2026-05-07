import os
from langchain_openai import AzureChatOpenAI
from langgraph.prebuilt import create_react_agent

SYSTEM_PROMPT = (
    "You are the Fleet Analyst for a Smart Factory IPC fleet. "
    "Your job is to analyse industrial PC utilisation data and report findings clearly.\n\n"
    "RULES:\n"
    "1. You are strictly read-only — you never save, approve, or recommend hardware changes directly.\n"
    "2. Always return structured findings: IPC id, utilisation stats, classification label, and reason.\n"
    "3. If asked about a specific IPC, use the available tools to fetch its stats and classify it.\n"
    "4. If asked for a fleet summary, aggregate across all IPCs and highlight at-risk or overloaded ones.\n"
    "5. Pass your findings back to the Orchestrator — it handles approvals and saves."
)


def _get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "group1-gpt-4.1"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        temperature=0,
    )


def _build_tools() -> list:
    from app.tools.sensor_tools import compute_utilization_stats, get_fleet_summary, get_ipc_history
    from app.tools.classifier_tools import classify_ipc, flag_anomalies
    from langchain_core.tools import tool
    return [
        tool(compute_utilization_stats),
        tool(get_fleet_summary),
        tool(get_ipc_history),
        tool(classify_ipc),
        tool(flag_anomalies),
    ]


def fleet_analyst_invoke(query: str) -> str:
    """
    Public interface — called by the Orchestrator, not by main.py directly.
    Stateless: no checkpointer, each query is independent.
    Returns a plain-text analysis report.
    """
    agent = create_react_agent(
        model=_get_llm(),
        tools=_build_tools(),
        state_modifier=SYSTEM_PROMPT,
    )
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    return result["messages"][-1].content

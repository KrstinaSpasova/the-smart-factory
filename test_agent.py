"""
Quick smoke test — run from project root:
    python test_agent.py
"""
from dotenv import load_dotenv
load_dotenv()

from backend.app.agents.orchestrator import orchestrator_invoke

print("=== Test 1: basic question ===")
result = orchestrator_invoke("Hello, what can you help me with?", session_id="test")
print("Reply:", result["reply"])
print("Trace ID:", result["trace_id"])

print("\n=== Test 2: HITL check — should ask for approval ===")
result2 = orchestrator_invoke("I want to decommission IPC-001", session_id="test")
print("Reply:", result2["reply"])
print("Trace ID:", result2["trace_id"])

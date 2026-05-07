import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# One orchestrator instance per session_id.  K's create_orchestrator() is
# imported lazily so the app boots even before K's branch is merged.
_sessions: dict[str, Any] = {}


def _langfuse_handler():
    """Return a LangFuse CallbackHandler if keys are configured, else None."""
    try:
        from langfuse.callback import CallbackHandler

        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        sk = os.getenv("LANGFUSE_SECRET_KEY", "")
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        if pk and sk and not pk.startswith("pk-lf-..."):
            return CallbackHandler(public_key=pk, secret_key=sk, host=host)
    except Exception:
        pass
    return None


def _get_orchestrator(session_id: str):
    if session_id not in _sessions:
        from app.agents.orchestrator import create_orchestrator
        _sessions[session_id] = create_orchestrator()
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Smart Factory Operations Center",
    description="Multi-agent IPC fleet management assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models (schema agreed with K — do not rename fields)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    session_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Main chat endpoint.  Passes the message to the Orchestrator agent, which
    manages ConversationBufferMemory per session and enforces HITL.
    LangFuse traces the full call tree automatically via the callback.
    """
    handler = _langfuse_handler()
    callbacks = [handler] if handler else []

    try:
        orchestrator = _get_orchestrator(req.session_id)
        result = orchestrator.invoke(
            req.message,
            config={
                "callbacks": callbacks,
                "run_name": f"session_{req.session_id}",
            },
        )
        # AgentExecutor returns {"output": "..."}, plain agents return str
        reply = result if isinstance(result, str) else result.get("output", str(result))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(reply=reply, session_id=req.session_id)


@app.get("/fleet/summary")
def fleet_summary():
    """
    Returns fleet-wide classification counts directly from the sensor tools
    without going through the chat agent — useful for dashboard widgets.
    """
    try:
        from app.tools.sensor_tools import get_fleet_summary
        return get_fleet_summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/ipc/{ipc_id}/history")
def ipc_history(ipc_id: str, days: int = 30):
    """
    Raw time-series CPU utilisation for a single IPC over the last `days` days.
    """
    try:
        from app.tools.sensor_tools import get_ipc_history
        return get_ipc_history(ipc_id, days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/decisions")
def decisions():
    """
    All operator decisions persisted in SQLite — approved, rejected, deferred.
    """
    try:
        from app.tools.memory_tools import load_past_decisions
        return load_past_decisions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Smart Factory Operations Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    trace_id: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        from app.agents.orchestrator import orchestrator_invoke
        result = orchestrator_invoke(req.message, req.session_id)
        return ChatResponse(
            reply=result["reply"],
            session_id=result["session_id"],
            trace_id=result.get("trace_id"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/fleet/summary")
def fleet_summary():
    try:
        from app.tools.sensor_tools import get_fleet_summary
        return get_fleet_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ipc/{ipc_id}/history")
def ipc_history(ipc_id: str, days: int = 30):
    try:
        from app.tools.sensor_tools import get_ipc_history
        records = get_ipc_history(ipc_id, days)
        return {"ipc_id": ipc_id, "records": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/decisions")
def decisions():
    try:
        from app.tools.memory_tools import load_past_decisions
        return load_past_decisions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

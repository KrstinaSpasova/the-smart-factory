from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Smart Factory Operations Center")


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # TODO: wire to orchestrator agent
    return ChatResponse(reply=f"[stub] received: {req.message}", session_id=req.session_id)


@app.get("/fleet/summary")
def fleet_summary():
    # TODO: wire to Fleet Analyst tool
    return {"summary": "not implemented"}


@app.get("/ipc/{ipc_id}/history")
def ipc_history(ipc_id: str):
    # TODO: wire to sensor tool
    return {"ipc_id": ipc_id, "history": []}


@app.get("/decisions")
def decisions():
    # TODO: wire to memory tool (SQLite)
    return {"decisions": []}

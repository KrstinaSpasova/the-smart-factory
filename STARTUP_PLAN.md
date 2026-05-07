# Plan to bring the app up

Phased plan for resolving the issues blocking `docker compose up --build` and getting the full HITL flow working end-to-end.

Decision recorded: **Azure OpenAI** is the LLM provider (keeping K's `AzureChatOpenAI` code; `.env.example` will be updated to match).

---

## Issues found

| # | Issue | File(s) | Severity |
|---|---|---|---|
| 1 | `from langchain.agents import create_agent` — that symbol doesn't exist; LangGraph's API is `langgraph.prebuilt.create_react_agent` | `agents/orchestrator.py`, `agents/fleet_analyst.py` | **Blocker** (import error at startup) |
| 2 | `langgraph` missing from `requirements.txt` | `backend/requirements.txt` | **Blocker** |
| 3 | Imports use `backend.app.…` prefix, but the Docker WORKDIR is `/app` and uvicorn runs `app.main:app` — root package is `app.` | `agents/orchestrator.py` | **Blocker** |
| 4 | `_build_tools()` returns `[]` in both agents — agent has nothing to call | `agents/orchestrator.py`, `agents/fleet_analyst.py` | **Functional** (app starts, agent useless) |
| 5 | `memory_manager.py` is all stubs — won't actually persist anything | `agents/memory_manager.py` | **Functional** |
| 6 | `main.py` `/chat` returns a stub string, never invokes the orchestrator; other endpoints same | `app/main.py` | **Functional** |
| 7 | `.env.example` lists `GROQ_*` vars but K's agent code uses `AzureChatOpenAI` reading `AZURE_OPENAI_*` | `.env.example` | **Config mismatch** |
| 8 | Tool functions lack docstrings — `langchain_core.tools.tool(fn)` uses the docstring as the LLM-visible description | `tools/sensor_tools.py`, `classifier_tools.py`, `memory_tools.py` | **Quality** (LLM picks tools poorly) |
| 9 | Building a fresh agent + checkpointer on every `/chat` call is wasteful but harmless — leave for MVP | `orchestrator.py` | **Defer** |

K's `from langfuse.langchain import CallbackHandler` and bare `CallbackHandler()` constructor are **correct** for langfuse v3.x — leave alone.

---

## Phase 1 — Make it import

**Goal:** `docker compose up --build` succeeds, server starts cleanly, `/health` returns ok.

1. **`backend/requirements.txt`** — add `langgraph` (already done).
2. **`agents/orchestrator.py`**:
   - Replace `from langchain.agents import create_agent` → `from langgraph.prebuilt import create_react_agent`.
   - Rewrite `from backend.app.agents.memory_manager import …` → `from app.agents.memory_manager import …`.
   - In `orchestrator_invoke`, change `create_agent(..., system_prompt=system, checkpointer=…)` → `create_react_agent(..., state_modifier=system, checkpointer=…)`. (`state_modifier` is the LangGraph param name; takes `str | SystemMessage | callable`.)
   - Wrap `langfuse_handler.last_trace_id` in `getattr(handler, "last_trace_id", None)` to tolerate version drift.
3. **`agents/fleet_analyst.py`** — same `create_agent → create_react_agent` and `system_prompt → state_modifier` swaps.
4. **`.env.example`** — replace the Groq block with:
   ```env
   AZURE_OPENAI_API_KEY=...
   AZURE_OPENAI_ENDPOINT=https://....openai.azure.com
   AZURE_OPENAI_DEPLOYMENT=group1-gpt-4.1
   AZURE_OPENAI_API_VERSION=2024-12-01-preview
   ```

**Validation:** `docker compose up --build backend`. Check logs for clean uvicorn startup, no `ImportError`. `curl http://localhost:8000/health` → `{"status":"ok"}`.

---

## Phase 2 — Wire tools into agents

**Goal:** Agent can answer a fleet question by calling real tools.

5. **`tools/sensor_tools.py`** — add one-line docstrings to `compute_utilization_stats`, `get_fleet_summary`, `get_ipc_history`. (`load_sensor_data` is internal — won't be exposed as a tool.)
6. **`tools/classifier_tools.py`** — add docstrings to `classify_ipc`, `flag_anomalies`.
7. **`tools/memory_tools.py`** — add docstrings to `save_decision`, `load_past_decisions`. (`get_session_context` is called directly by the orchestrator, not as a tool.)
8. **`agents/memory_manager.py`** — uncomment the imports, replace the three stub bodies with delegations to `_save`, `_load`, `_get_context`.
9. **`agents/orchestrator.py` `_build_tools()`** — uncomment, fix `backend.app.` → `app.`, return the wrapped list:
   ```python
   from app.tools.sensor_tools import compute_utilization_stats, get_fleet_summary, get_ipc_history
   from app.tools.classifier_tools import classify_ipc, flag_anomalies
   from app.tools.memory_tools import load_past_decisions, save_decision
   from langchain_core.tools import tool
   return [tool(compute_utilization_stats), tool(classify_ipc),
           tool(get_fleet_summary), tool(get_ipc_history),
           tool(flag_anomalies), tool(load_past_decisions), tool(save_decision)]
   ```
10. **`agents/fleet_analyst.py` `_build_tools()`** — same pattern, sensor + classifier tools only (read-only agent, no memory_tools).

**Validation:** `docker compose up --build` then in Streamlit ask "Give me a fleet summary." Expect a tool-call → real numbers (~4261 IPCs).

---

## Phase 3 — Wire FastAPI endpoints

**Goal:** `/chat`, `/fleet/summary`, `/decisions`, `/ipc/{id}/history` all return real data; full HITL flow works end-to-end.

11. **`app/main.py`**:
    - `/chat` → call `app.agents.orchestrator.orchestrator_invoke(req.message, req.session_id)`; map result to `ChatResponse` (add `trace_id` field if you want it surfaced).
    - `/fleet/summary` → `app.tools.sensor_tools.get_fleet_summary()`.
    - `/ipc/{ipc_id}/history` → `app.tools.sensor_tools.get_ipc_history(ipc_id)`.
    - `/decisions` → `app.tools.memory_tools.load_past_decisions()`.
    - Wrap each in `try/except HTTPException(500, str(e))` so a missing CSV / DB doesn't crash uvicorn.

**Validation:** Run end-to-end HITL flow from Streamlit: "Which IPCs are at risk?" → agent proposes → "approve ITLT4301" → check `/decisions` shows the row.

---

## Risks / things to watch

- **`get_fleet_summary()` is slow**: it iterates all 4,261 IPCs and calls `classify_ipc` (which calls `compute_utilization_stats`) per IPC. First call could take 10–30s. Acceptable for MVP; if it's painful, vectorise later.
- **`state_modifier` may be renamed `prompt`** in very recent LangGraph (≥ 0.3.5). If Phase 1 fails on that arg, swap the keyword.
- **`langfuse_handler.last_trace_id`**: not guaranteed across versions — that's why we wrap it in `getattr`.
- **CSV mount**: `docker-compose.yml` mounts both `./data:/app/data` *and* the file at `:/app/data/sensor_data.csv:ro`. The file mount wins for that path, `memory.db` stays writable from the dir mount. Already verified the file exists.

---

## Out of scope (defer)

- Caching the compiled agent across requests (perf, not correctness).
- Vectorising `get_fleet_summary`.
- Adding `flag_anomalies` to `/fleet/summary` response.
- Anything labelled "safe to cut" in `TASK_SPLIT.md`.

# Task Split — Smart Factory (3-hour sprint)

## Stack deltas from ARCHITECTURE.md

| Change | Decision |
|---|---|
| Frontend | ~~React/Vite~~ → **Streamlit** (Python, replaces `frontend/` entirely) |
| LLM provider | ~~Anthropic~~ → **OpenAI** (`langchain-openai`, `OPENAI_API_KEY`) |
| Agent framework | Plain **LangChain** (no LangGraph — MVP only) |
| Data mount | Create `the-smart-factory/data/` and place CSV there (blocker fix from inconsistencies.md) |
| Docker | Drop `frontend` Node service; add `streamlit` Python service |

---

## People

| ID | Strength | Role |
|---|---|---|
| **K** | LangChain expert | Agent layer (Orchestrator + Fleet Analyst + LangFuse wiring) |
| **M** | Data science, so-so stack | Data + tools layer (pandas, classifier, SQLite) |
| **J** | Strong fundamentals, stack-unfamiliar | Infrastructure + frontend (FastAPI skeleton, Streamlit UI, Docker, README) |

J gets the tasks with the flattest LangChain surface — FastAPI and Streamlit are dead-simple HTTP/Python with no LangChain concepts.

---

## Timeline

```
T+0:00  ──── Kickoff: J fixes data/ dir blocker; everyone starts in parallel
T+1:00  ──── Sync: M hands sensor_tools.py to K; J wires /chat stub
T+2:00  ──── Sync: K hands working agent to J; M hands memory_tools.py to K
T+3:00  ──── Submit: Docker build green; full HITL flow demo-able
```

---

## K — Agent layer

**Owns:** `backend/app/agents/`

### Hour 1 (0:00–1:00)

- [ ] `requirements.txt`: replace `langchain-anthropic` → `langchain-openai`
- [ ] `agents/orchestrator.py`: scaffold `AgentExecutor` with `ChatOpenAI`, `ConversationBufferMemory`, and the system prompt (HITL rules, memory context injection). Stub tool list — real tools arrive from M in hour 2.
- [ ] `agents/fleet_analyst.py`: scaffold read-only sub-agent; no tools yet.

### Hour 2 (1:00–2:00)

- [ ] Wire M's `sensor_tools` and `classifier_tools` into Fleet Analyst.
- [ ] Wire M's `memory_tools` into Orchestrator (`load_past_decisions`, `save_decision`, `get_session_context`).
- [ ] `agents/memory_manager.py`: thin wrapper calling memory_tools (can be plain functions at MVP — see ARCHITECTURE.md §7.4).
- [ ] HITL logic: approval keyword detection in Orchestrator; `save_decision` only called after affirmative.

### Hour 3 (2:00–3:00)

- [ ] LangFuse: instantiate `CallbackHandler` in `main.py`; pass via `config={"callbacks": [...]}` in every `agent.invoke()`.
- [ ] `ConversationBufferMemory(memory_key="chat_history", return_messages=True)` — confirm it passes correctly per ARCHITECTURE.md §12.
- [ ] End-to-end smoke test: ask "which IPCs are at risk?", approve one, confirm it lands in SQLite.
- [ ] Return `agent_trace_id` in `ChatResponse`.

**Key reference:** ARCHITECTURE.md §7, §11, §12.

---

## M — Data + tools layer

**Owns:** `backend/app/tools/`, `backend/app/classifier/`

### Hour 1 (0:00–1:00)

- [ ] **Blocker fix:** create `the-smart-factory/data/` and copy/move the CSV into it (fixes the Docker mount — inconsistencies.md #4).
- [ ] `tools/sensor_tools.py`:
  - `load_sensor_data(ipc_id=None)` — CSV load with correct params (`sep=';'`, `decimal=','`, `dayfirst=True`), extract `cpu_mhz_rated`, compute `cpu_pct`, drop outliers (`cpu_pct > 100`).
  - `compute_utilization_stats(ipc_id)` → `{mean, p50, p95, max}`.
  - `get_fleet_summary()` → `{total_ipcs, count_per_label, factory_breakdown}`.
  - `get_ipc_history(ipc_id, days=30)` → list of `{date, cpu_pct}`.

### Hour 2 (1:00–2:00)

- [ ] `tools/classifier_tools.py`:
  - `classify_ipc(ipc_id)` — hardcoded thresholds on `cpu_p95`:  
    `< 30% → underutilized`, `30–65% → healthy`, `65–85% → at_risk`, `≥ 85% → overloaded`.  
    Returns `{label, rule_fired, cpu_p95}`.
  - `flag_anomalies(ipc_id=None)` — `cpu_p95 > 85%` OR `days_observed < 10`.
- [ ] `classifier/rules.json` — hardcode the four threshold rules in the JSON format from ARCHITECTURE.md §9.2.
- [ ] `tools/memory_tools.py`:
  - SQLite init (`decisions` + `preferences` tables — schema in ARCHITECTURE.md §10.2).
  - `save_decision(ipc_id, action, rationale, status, operator_note=None)`.
  - `load_past_decisions(ipc_id=None)`.
  - `get_session_context()` → plain-text summary of last 10 decisions.

### Hour 3 (2:00–3:00)

- [ ] Test data pipeline end-to-end in isolation (no agents): load CSV → compute stats for 2–3 IPCs → classify → save a dummy decision → read it back.
- [ ] Confirm `get_fleet_summary()` returns plausible numbers (~4261 IPCs, realistic label split).
- [ ] Help K debug any tool-wiring issues.

**Key reference:** ARCHITECTURE.md §3, §8, §10.

---

## J — Infrastructure + frontend

**Owns:** `backend/app/main.py`, `frontend/app.py` (Streamlit), `docker-compose.yml`, `.env.example`, `README.md`

### Hour 1 (0:00–1:00)

- [ ] `docker-compose.yml`: remove the `frontend` Node service; add a `streamlit` service:
  ```yaml
  streamlit:
    build: ./frontend
    ports: ["8501:8501"]
    depends_on: [backend]
    environment:
      - BACKEND_URL=http://backend:8000
  ```
- [ ] `frontend/Dockerfile`: replace Node image with `python:3.11-slim`; install `streamlit requests`; `CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]`.
- [ ] `.env.example`: replace `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` with `OPENAI_API_KEY` / `OPENAI_MODEL` (default `gpt-4o-mini`); keep all LangFuse + path vars.
- [ ] `backend/app/main.py`: scaffold FastAPI app with all 4 routes stubbed (return placeholder JSON so Docker build passes):
  - `POST /chat` — body: `{session_id, message}`; response: `{session_id, response, agent_trace_id}`.
  - `GET /fleet/summary`
  - `GET /ipc/{ipc_id}/history`
  - `GET /decisions`

### Hour 2 (1:00–2:00)

- [ ] `frontend/app.py` (Streamlit chat UI):
  ```python
  import streamlit as st, requests, os, uuid

  BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")

  if "session_id" not in st.session_state:
      st.session_state.session_id = str(uuid.uuid4())
  if "messages" not in st.session_state:
      st.session_state.messages = []

  st.title("Smart Factory Operations Center")

  for msg in st.session_state.messages:
      with st.chat_message(msg["role"]):
          st.markdown(msg["content"])

  if prompt := st.chat_input("Ask about your IPC fleet..."):
      st.session_state.messages.append({"role": "user", "content": prompt})
      with st.chat_message("user"):
          st.markdown(prompt)
      with st.chat_message("assistant"):
          with st.spinner("Thinking..."):
              r = requests.post(f"{BACKEND}/chat",
                                json={"session_id": st.session_state.session_id, "message": prompt})
              reply = r.json()["response"] if r.ok else f"Error: {r.status_code}"
          st.markdown(reply)
      st.session_state.messages.append({"role": "assistant", "content": reply})
  ```
- [ ] Wire `POST /chat` in `main.py` to the Orchestrator (K should have the agent working by now — call `orchestrator.invoke(...)`).
- [ ] Wire `GET /fleet/summary` and `GET /decisions` to tool calls (M's `get_fleet_summary()` and `load_past_decisions()`).

### Hour 3 (2:00–3:00)

- [ ] `GET /ipc/{ipc_id}/history` — wire to `get_ipc_history(ipc_id)`.
- [ ] Run `docker compose up --build` and confirm both services start cleanly.
- [ ] `README.md`:
  - Prerequisites: Docker, API keys.
  - Setup: `cp .env.example .env`, fill keys, `docker compose up --build`.
  - URLs: `http://localhost:8501` (chat), `http://localhost:8000/docs` (API).
  - Brief agent design description (2–3 sentences).
- [ ] CORS: add `CORSMiddleware` to FastAPI if Streamlit → backend calls fail.

**Key reference:** ARCHITECTURE.md §6, §13, §14, §15.

---

## Dependency graph

```
M: sensor_tools ──────────────────────┐
M: classifier_tools ──────────────────┤──► K: Fleet Analyst ──► K: Orchestrator ──► J: /chat wired
M: memory_tools ──────────────────────┘                                          │
J: main.py stub (no deps, hour 1) ─────────────────────────────────────────────►┘
J: Streamlit shell (no deps, hour 2)───────────────────────────────── calls /chat
```

M → K handoff happens at T+1:00. K → J handoff at T+2:00. Everything else is parallel.

---

## What to cut if running late

| Feature | Cut? | Notes |
|---|---|---|
| `flag_anomalies` tool | Safe to cut | Not called by MVP Orchestrator flow |
| `get_ipc_history` endpoint | Safe to cut | Dashboard-only; not needed for chat |
| `preferences` SQLite table | Safe to cut | Only needed for Good tier |
| LangFuse | Keep if possible | Just one callback line — fast to add |
| `get_fleet_summary` endpoint | Keep | Used by Streamlit sidebar optionally |
| Streamlit sidebar/extras | Cut freely | Bare chat input is sufficient |

---

## Environment variables (final `.env.example`)

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

BACKEND_PORT=8000
FRONTEND_PORT=8501
SENSOR_DATA_PATH=/app/data/sensor_data.csv
DATABASE_PATH=/app/data/memory.db
```

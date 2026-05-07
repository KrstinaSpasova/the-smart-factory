# Smart Factory Operations Center — Architecture

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Tech Stack](#2-tech-stack)
3. [Data](#3-data)
4. [Project Structure](#4-project-structure)
5. [MVP Feature Map](#5-mvp-feature-map)
6. [Backend Architecture](#6-backend-architecture)
7. [Agent Design](#7-agent-design)
8. [Tool Catalogue](#8-tool-catalogue)
9. [Classifier Pipeline](#9-classifier-pipeline)
10. [Memory System](#10-memory-system)
11. [Human-in-the-Loop](#11-human-in-the-loop)
12. [Observability](#12-observability)
13. [API Reference](#13-api-reference)
14. [Frontend](#14-frontend)
15. [Docker & Deployment](#15-docker--deployment)
16. [Environment Variables](#16-environment-variables)
17. [Build Status](#17-build-status)

---

## 1. System Overview

The Smart Factory Operations Center is a multi-agent AI backend that analyzes IPC (Industrial PC) sensor data from pizza production lines across Europe, reasons about fleet health, and guides operators through data-driven right-sizing decisions — always with human approval before any action is persisted.

**Core loop:**

```
Operator types a message
    → FastAPI /chat endpoint receives it
    → Orchestrator agent routes to Fleet Analyst and/or Recommendation Engine
    → Results are formatted and surfaced to the operator as a reviewable proposal
    → Operator approves or rejects
    → Memory Manager persists the decision to SQLite
    → LangFuse records the full trace
```

---

## 2. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Agent framework | LangChain | `langchain`, `langchain-anthropic` |
| LLM | Anthropic Claude (via `langchain-anthropic`) | Model configurable via `ANTHROPIC_MODEL` env var |
| Observability | LangFuse | `langfuse`; callbacks registered at agent level |
| Data analysis | pandas | CSV loading, stats, filtering |
| Persistence | SQLite | Standard library `sqlite3`; file at `data/memory.db` |
| Backend API | FastAPI + uvicorn | `fastapi`, `uvicorn[standard]` |
| Request validation | Pydantic | Bundled with FastAPI |
| Config | python-dotenv | `.env` loading |
| Frontend | React (Vite) | Node 20-alpine Docker image |
| Containerization | Docker + docker-compose | Two services: `backend`, `frontend` |

**Full backend dependency list** (`backend/requirements.txt`):

```
langchain
langchain-anthropic
langfuse
pandas
openpyxl
fastapi
uvicorn[standard]
python-dotenv
pydantic
```

---

## 3. Data

### 3.1 Source File

**File:** `Database - Testcase_agentic_ai_V1.0.zip.csv` (root of repo)  
**Encoding:** UTF-8  
**Delimiter:** semicolon (`;`)  
**Decimal separator:** comma (`,`) — European format  
**Parsing:** `pd.read_csv(..., sep=';', decimal=',')`

At runtime the file is mounted into the backend container and referenced by `SENSOR_DATA_PATH`.

### 3.2 Schema

| Column | Type | Description |
|---|---|---|
| `IPC` | string | IPC identifier (e.g. `ITLT4301`) |
| `Data Factory` | int | Factory ID, values 1–5 |
| `time` | string → datetime | Date in `DD/MM/YYYY` format |
| `AvgValue` | float | Mean CPU usage that day (MHz) |
| `MinValue` | float | Minimum CPU usage that day (MHz) |
| `MaxValue` | float | Maximum CPU usage that day (MHz) |
| `MetricId` | string | Always `CpuUsageMHz` (drop at load time) |
| `CpuMHz` | string/mixed | Rated CPU clock frequency; some IPCs report composite strings like `"5600 3200"` (multi-CPU) |

### 3.3 Key Facts from EDA

- **220,294 rows** total
- **4,261 unique IPCs** across **5 factories**
- **Date range:** 1 May – 30 June 2021 (61 days); median 54 records per IPC (irregular series)
- `AvgValue`, `MinValue`, `MaxValue` are highly collinear (Spearman ≈ 0.9+) — `AvgValue` is the primary feature
- Distribution is **right-skewed**; use p95 aggregation, not mean, to represent peak load
- **Factory 5 outliers:** IPC `ITLT1593` reports `AvgValue > 300,000 MHz` on a 9,600 MHz rated CPU — data quality anomaly flagged, exclude from classifier training
- **261 rows** have composite `CpuMHz` strings (multi-CPU IPCs) — extract the first numeric token for the rated clock

### 3.4 Derived Feature Used for Classification

At inference time, each IPC is represented as a single aggregated row:

| Feature | Derivation |
|---|---|
| `cpu_p95` | 95th percentile of `AvgValue / CpuMHz * 100` (utilization %) |
| `cpu_avg` | Mean of `AvgValue / CpuMHz * 100` |
| `cpu_max` | Max of `AvgValue / CpuMHz * 100` |
| `days_observed` | Count of rows for this IPC (data completeness proxy) |

`AvgValue` is in MHz; dividing by the rated `CpuMHz` converts it to a 0–100% utilization figure.

---

## 4. Project Structure

```
the-smart-factory/
├── ASSIGNMENT.md                    # Full design specification
├── PRIORITIES.md                    # MVP / Good / Best feature tiers
├── ARCHITECTURE.md                  # This document
├── docker-compose.yml               # Backend + frontend services
├── .env.example                     # All required env vars
├── .gitignore
│
├── Database - Testcase_agentic_ai_V1.0.zip.csv   # Raw sensor data (16 MB)
│
├── EDA/                             # Exploratory data analysis (completed)
│   ├── eda_v1.py                    # Basic shape / dtypes / describe
│   ├── eda_v2.py                    # Correct parsing (sep=';', decimal=',')
│   ├── eda_v3.py                    # Integrity, outliers, time coverage
│   ├── eda_v4.py                    # ASCII-safe version of v3 (Windows console)
│   └── eda_v5.ipynb                 # Visual notebook: histograms, boxplots, heatmaps, time-series
│
├── backend/
│   ├── Dockerfile                   # python:3.11-slim, uvicorn on port 8000
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       ├── main.py                  # FastAPI app + route definitions
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── orchestrator.py      # Entry point agent; routes, enforces HITL
│       │   ├── fleet_analyst.py     # Read-only sensor analysis
│       │   ├── recommendation_engine.py
│       │   └── memory_manager.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── sensor_tools.py      # load_sensor_data, compute_utilization_stats, …
│       │   ├── classifier_tools.py  # classify_ipc, flag_anomalies
│       │   ├── recommendation_tools.py
│       │   └── memory_tools.py
│       ├── classifier/
│       │   ├── train_classifier.py  # k-means → decision tree → rules.json (Good tier)
│       │   └── rules.json           # IF/THEN rules loaded at runtime
│       └── data/
│           └── sensor_data.csv      # Symlink / copy of raw CSV
│
├── frontend/
│   ├── Dockerfile                   # node:20-alpine, npm start on port 3000
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   └── src/
│       └── App.jsx                  # Chat UI component
│
└── data/                            # Docker volume mount point
    └── memory.db                    # SQLite file (auto-created, gitignored)
```

---

## 5. MVP Feature Map

The following is the complete MVP feature set from `PRIORITIES.md`, mapped to implementation locations.

| # | MVP Feature | Location |
|---|---|---|
| 1 | Chat interface — single page, send message + see reply | `frontend/src/App.jsx` |
| 2 | FastAPI backend with `/chat` endpoint | `backend/app/main.py` |
| 3 | Orchestrator + Fleet Analyst agents | `backend/app/agents/orchestrator.py`, `fleet_analyst.py` |
| 4 | Load sensor CSV into pandas | `backend/app/tools/sensor_tools.py` → `load_sensor_data` |
| 5 | Basic utilization stats tool (mean, p95 per IPC) | `backend/app/tools/sensor_tools.py` → `compute_utilization_stats` |
| 6 | Hardcoded threshold classifier (CPU cutoffs) | `backend/app/tools/classifier_tools.py` → `classify_ipc` |
| 7 | Simple recommendation output in chat | `backend/app/agents/orchestrator.py` (formats output) |
| 8 | HITL: agent asks "approve?" before any "save" | `backend/app/agents/orchestrator.py` (enforced in system prompt + logic) |
| 9 | SQLite `decisions` table — save approved/rejected | `backend/app/tools/memory_tools.py` → `save_decision` |
| 10 | LangChain `ConversationBufferMemory` | `backend/app/agents/orchestrator.py` |
| 11 | LangFuse callback registered on agent | `backend/app/main.py` or agent constructors |
| 12 | `docker-compose.yml` with backend + frontend | `docker-compose.yml` |
| 13 | README with setup steps | `README.md` |
| 14 | `.env.example` with all required keys | `.env.example` |

---

## 6. Backend Architecture

### 6.1 FastAPI Application (`main.py`)

Entry point. Exposes REST endpoints and wires up the Orchestrator.

```
POST /chat
GET  /fleet/summary
GET  /ipc/{ipc_id}/history
GET  /decisions
GET  /docs          (FastAPI auto-generated OpenAPI UI)
```

Session state is held per `session_id` in an in-process dict. Each session carries its own `ConversationBufferMemory` instance and one Orchestrator agent.

### 6.2 Request / Response Models (Pydantic)

```python
class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    agent_trace_id: str | None
```

### 6.3 LangFuse Integration

A `CallbackHandler` from `langfuse.callback` is instantiated once per request and passed to the agent's `invoke` call via the `config={"callbacks": [...]}` parameter. This captures all child spans automatically — no per-tool instrumentation required.

---

## 7. Agent Design

### 7.1 Orchestrator

**File:** `backend/app/agents/orchestrator.py`  
**Type:** LangChain `AgentExecutor` with `ConversationBufferMemory`

**Responsibilities:**
- Sole interface to the chat endpoint — the operator never talks to other agents directly
- Decides whether to call Fleet Analyst, Recommendation Engine, or Memory Manager based on the operator message
- Formats agent outputs into clear, human-reviewable proposals
- Enforces HITL: never calls `save_decision` without an explicit affirmative from the operator
- Injects long-term memory context (last N decisions, operator preferences) at session start via `get_session_context`

**System prompt (excerpt):**
```
You are the Smart Factory Operations Center assistant.
You help operators make data-driven decisions about IPC fleet management.

You NEVER record or act on a recommendation without explicit operator approval.
When you have a recommendation, present it clearly with the supporting reasoning
and ask the operator to approve, reject, or adjust before proceeding.

Before making recommendations, check past decisions to avoid re-suggesting
previously rejected actions.

{memory_context}
```

**Memory:** `ConversationBufferMemory(memory_key="chat_history", return_messages=True)`

---

### 7.2 Fleet Analyst

**File:** `backend/app/agents/fleet_analyst.py`  
**Type:** LangChain tool-calling agent (read-only; no DB access)

**Responsibilities:**
- Loads and queries the sensor CSV via pandas tools
- Computes per-IPC and fleet-wide statistics
- Classifies IPCs using the threshold rules
- Returns structured facts — never recommendations

**Tools available:** `load_sensor_data`, `compute_utilization_stats`, `classify_ipc`, `flag_anomalies`, `get_fleet_summary`, `get_ipc_history`

---

### 7.3 Recommendation Engine (MVP: inline in Orchestrator)

For the MVP the recommendation logic lives directly in the Orchestrator's system prompt and tool calls rather than in a separate agent. The Orchestrator calls `classify_ipc` and formats the result into a ranked proposal. A dedicated `RecommendationEngine` agent is introduced in the Good tier.

---

### 7.4 Memory Manager

**File:** `backend/app/agents/memory_manager.py` (MVP: thin wrapper; may be plain function calls)  
**Storage:** SQLite at `data/memory.db`

Handles all reads and writes to long-term storage. Called only by the Orchestrator after explicit operator approval.

---

## 8. Tool Catalogue

### 8.1 Sensor Tools (`sensor_tools.py`)

| Tool | Signature | Returns |
|---|---|---|
| `load_sensor_data` | `(ipc_id: str \| None = None)` | DataFrame filtered to one IPC or full fleet |
| `compute_utilization_stats` | `(ipc_id: str)` | `{mean, p50, p95, max}` of CPU utilisation % for that IPC |
| `get_fleet_summary` | `()` | `{total_ipcs, count_per_label, factory_breakdown}` |
| `get_ipc_history` | `(ipc_id: str, days: int = 30)` | List of `{date, cpu_pct}` dicts for time-series display |

**CSV loading convention:**

```python
df = pd.read_csv(path, sep=';', decimal=',')
df['time'] = pd.to_datetime(df['time'], format='%d/%m/%Y')
df['cpu_mhz_rated'] = df['CpuMHz'].astype(str).str.extract(r'(\d+)').astype(float)
df['cpu_pct'] = df['AvgValue'] / df['cpu_mhz_rated'] * 100
df = df[df['cpu_pct'] <= 100]   # drop known outliers (ITLT1593 etc.)
```

---

### 8.2 Classifier Tools (`classifier_tools.py`)

#### `classify_ipc(ipc_id: str) → dict`

MVP implementation uses hardcoded thresholds derived from the EDA findings:

```
cpu_p95 < 30%              → underutilized
30% ≤ cpu_p95 < 65%        → healthy
65% ≤ cpu_p95 < 85%        → at_risk
cpu_p95 ≥ 85%              → overloaded
```

Returns:
```json
{
  "label": "at_risk",
  "rule_fired": "cpu_p95 >= 65% AND cpu_p95 < 85%",
  "cpu_p95": 71.3
}
```

#### `flag_anomalies(ipc_id: str | None = None) → list`

Returns IPCs whose `cpu_p95 > 85%` or whose `days_observed < 10` (sparse data).

---

### 8.3 Recommendation Tools (MVP: inline logic)

For the MVP, recommendation generation is handled in the Orchestrator's prompt. The following rules govern the proposal text:

| Classification | Proposed Action |
|---|---|
| `overloaded` | Urgent hardware review or workload redistribution |
| `at_risk` | Schedule inspection; monitor closely |
| `healthy` | No action required |
| `underutilized` | Downgrade to next hardware tier at next maintenance window |

---

### 8.4 Memory Tools (`memory_tools.py`)

| Tool | Signature | Description |
|---|---|---|
| `save_decision` | `(ipc_id, action, rationale, status, operator_note=None)` | Insert row into `decisions` table |
| `load_past_decisions` | `(ipc_id: str \| None = None)` | SELECT from `decisions`; optional IPC filter |
| `get_session_context` | `()` | Return a plain-text summary of the last 10 decisions |

---

## 9. Classifier Pipeline

### 9.1 MVP: Hardcoded Thresholds

The MVP classifier uses static thresholds (see §8.2). No training step is required. Thresholds are set from EDA findings.

### 9.2 Good Tier: Data-Mined Rules

When time allows, replace the hardcoded thresholds with a trained decision tree:

**Step 1 — Aggregate features per IPC:**

```python
agg = df.groupby('IPC').agg(
    cpu_p95=('cpu_pct', lambda x: x.quantile(0.95)),
    cpu_avg=('cpu_pct', 'mean'),
    cpu_max=('cpu_pct', 'max'),
    days_observed=('time', 'nunique')
).reset_index()
```

**Step 2 — K-means clustering (k=4):**

```python
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

scaler = StandardScaler()
X = scaler.fit_transform(agg[['cpu_p95', 'cpu_avg', 'cpu_max']])
kmeans = KMeans(n_clusters=4, random_state=42)
agg['cluster'] = kmeans.fit_predict(X)
```

**Step 3 — Assign human labels to clusters** (inspect centroids):

```
Cluster with lowest cpu_p95  → "underutilized"
Cluster with cpu_p95 30–65%  → "healthy"
Cluster with cpu_p95 65–85%  → "at_risk"
Cluster with highest cpu_p95 → "overloaded"
```

**Step 4 — Decision tree distillation:**

```python
from sklearn.tree import DecisionTreeClassifier, export_text

dt = DecisionTreeClassifier(max_depth=4, random_state=42)
dt.fit(X, agg['label'])
rules_text = export_text(dt, feature_names=['cpu_p95', 'cpu_avg', 'cpu_max'])
```

**Step 5 — Export to `rules.json`:**

```json
[
  {"conditions": [{"feature": "cpu_p95", "op": "<=", "value": 30.0}], "label": "underutilized"},
  {"conditions": [{"feature": "cpu_p95", "op": ">",  "value": 30.0},
                  {"feature": "cpu_p95", "op": "<=", "value": 65.0}], "label": "healthy"},
  ...
]
```

At runtime `classify_ipc` evaluates these rules in order and returns the first match plus the `rule_fired` string.

---

## 10. Memory System

### 10.1 Short-term (Session)

`LangChain ConversationBufferMemory` — stores the full message history of the current session. Passed as `chat_history` to the Orchestrator on every turn. Scoped to `session_id`; cleared when the session ends or the server restarts.

### 10.2 Long-term (SQLite)

**Database file:** `data/memory.db` (Docker volume; auto-created on first run)

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ipc_id        TEXT    NOT NULL,
    action        TEXT    NOT NULL,
    rationale     TEXT,
    status        TEXT    NOT NULL,      -- 'approved' | 'rejected' | 'deferred'
    operator_note TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
    key        TEXT PRIMARY KEY,
    value      TEXT    NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**How long-term memory feeds back into recommendations:**

1. At session start, `get_session_context()` returns a plain-text summary of the last 10 decisions.
2. This summary is injected into the Orchestrator's system prompt before the first message is processed.
3. Before proposing any action, the Orchestrator calls `load_past_decisions(ipc_id)` and checks for prior rejections. If one exists, it either skips that IPC or explicitly acknowledges the prior decision.

---

## 11. Human-in-the-Loop

HITL is enforced architecturally. The Orchestrator is the only agent that communicates with the operator, and it never calls `save_decision` without an explicit affirmative.

### Approval Keywords

The Orchestrator recognises natural language approval:
- **Approve:** "yes", "approve", "go ahead", "do it", "confirm", "approved"
- **Reject:** "no", "reject", "skip", "don't", "not now", "rejected"
- **Ambiguous:** anything else → the Orchestrator asks for clarification before saving

### Flow

```
Operator:      "Which IPCs should I be worried about?"

Orchestrator:  [calls classify_ipc for flagged IPCs]
               [calls load_past_decisions for each]

               "I found 2 IPCs needing attention:

               1. ITLT4301 (Factory 3) — OVERLOADED
                  CPU p95: 91%
                  Recommendation: Urgent hardware review or workload redistribution
                  Rule fired: cpu_p95 >= 85%

               2. ITLT2034 (Factory 1) — UNDERUTILIZED
                  CPU p95: 22%
                  Recommendation: Downgrade at next maintenance window
                  Rule fired: cpu_p95 < 30%

               Would you like to approve, reject, or adjust these recommendations?"

Operator:      "Approve ITLT4301. Reject ITLT2034 — new line next month."

Orchestrator:  [calls save_decision(ipc_id='ITLT4301', status='approved')]
               [calls save_decision(ipc_id='ITLT2034', status='rejected',
                                    operator_note='new line deployment next month')]

               "Understood. ITLT4301 escalated for urgent review.
               ITLT2034 deferred — noted the upcoming deployment."
```

---

## 12. Observability

### 12.1 LangFuse Setup

```python
from langfuse.callback import CallbackHandler

langfuse_handler = CallbackHandler(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST"),
)
```

The handler is passed to each `AgentExecutor.invoke()` call:

```python
agent.invoke(
    {"input": message, "chat_history": memory.load_memory_variables({})["chat_history"]},
    config={"callbacks": [langfuse_handler], "run_name": f"session_{session_id}"}
)
```

All child spans (tool calls, LLM calls) are captured automatically.

### 12.2 Trace Structure

```
Trace: session_{session_id}
  └── Span: orchestrator.run
        ├── Generation: orchestrator.llm_call
        ├── Event: tool.load_past_decisions
        ├── Event: tool.classify_ipc (× N)
        ├── Event: tool.get_fleet_summary
        └── Event: tool.save_decision      [only if HITL approved]
```

### 12.3 Configuration

Required environment variables:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 13. API Reference

### `POST /chat`

Send a message to the Orchestrator.

**Request:**
```json
{
  "session_id": "operator-001",
  "message": "Which IPCs are most at risk?"
}
```

**Response:**
```json
{
  "session_id": "operator-001",
  "response": "I found 3 IPCs classified as at_risk or overloaded...",
  "agent_trace_id": "trace-abc123"
}
```

---

### `GET /fleet/summary`

Returns current classification counts without going through the chat agent. Useful for a dashboard widget.

**Response:**
```json
{
  "total_ipcs": 4261,
  "healthy": 2841,
  "underutilized": 973,
  "at_risk": 331,
  "overloaded": 116
}
```

---

### `GET /ipc/{ipc_id}/history`

Raw time-series utilization for one IPC.

**Response:**
```json
{
  "ipc_id": "ITLT4301",
  "factory": 3,
  "records": [
    {"date": "2021-05-01", "cpu_pct": 87.3},
    {"date": "2021-05-02", "cpu_pct": 91.1}
  ]
}
```

---

### `GET /decisions`

All persisted operator decisions from SQLite.

**Response:**
```json
[
  {
    "id": 1,
    "ipc_id": "ITLT4301",
    "action": "Urgent hardware review",
    "status": "approved",
    "operator_note": null,
    "created_at": "2021-06-15T14:32:00"
  }
]
```

Interactive OpenAPI docs available at `http://localhost:8000/docs`.

---

## 14. Frontend

### Stack

- React 18 + Vite (bundler)
- Plain `fetch` for HTTP calls to the backend — no additional HTTP library needed
- CSS: minimal inline styles or a single stylesheet

### Component: `App.jsx`

Single-page chat interface:

1. **Message list** — renders conversation history; assistant messages containing "approve?" are visually distinguished
2. **Input bar** — text input + Send button; submits on Enter
3. **State** — `messages: [{role, content}]`, `sessionId: string`, `loading: bool`
4. **API call** — `POST http://backend:8000/chat` with `{session_id, message}` → append response to message list

The frontend does **not** parse the agent's output to extract structured data. All approval and rejection flows happen through natural-language chat messages forwarded to the backend.

### Vite proxy (for local dev)

```js
// vite.config.js
export default {
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: p => p.replace(/^\/api/, '') }
    }
  }
}
```

In Docker, `VITE_BACKEND_URL` is set to `http://backend:8000`.

---

## 15. Docker & Deployment

### `docker-compose.yml` (summary)

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes:
      - ./data:/app/data                          # SQLite persistence
      - ./Database - Testcase_agentic_ai_V1.0.zip.csv:/app/data/sensor_data.csv:ro
    env_file: .env

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
    environment:
      - VITE_BACKEND_URL=http://backend:8000
```

### Build & Run

```bash
cp .env.example .env
# fill in ANTHROPIC_API_KEY and LANGFUSE keys

docker-compose up --build
```

- Chat UI: `http://localhost:3000`
- API + docs: `http://localhost:8000/docs`

---

## 16. Environment Variables

All variables defined in `.env.example`:

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `ANTHROPIC_MODEL` | No | Defaults to `claude-sonnet-4-5` |
| `LANGFUSE_PUBLIC_KEY` | Yes | LangFuse project public key |
| `LANGFUSE_SECRET_KEY` | Yes | LangFuse project secret key |
| `LANGFUSE_HOST` | Yes | e.g. `https://cloud.langfuse.com` |
| `BACKEND_PORT` | No | Defaults to `8000` |
| `FRONTEND_PORT` | No | Defaults to `3000` |
| `SENSOR_DATA_PATH` | No | Defaults to `/app/data/sensor_data.csv` |
| `DATABASE_PATH` | No | Defaults to `/app/data/memory.db` |

---

## 17. Build Status

| Component | Status |
|---|---|
| EDA (v1–v5 scripts + notebook) | Done |
| docker-compose.yml | Done |
| backend/Dockerfile | Done |
| frontend/Dockerfile | Done |
| backend/requirements.txt | Done |
| .env.example | Done |
| ASSIGNMENT.md | Done |
| PRIORITIES.md | Done |
| backend/app/main.py | To build |
| backend/app/agents/orchestrator.py | To build |
| backend/app/agents/fleet_analyst.py | To build |
| backend/app/tools/sensor_tools.py | To build |
| backend/app/tools/classifier_tools.py | To build |
| backend/app/tools/memory_tools.py | To build |
| SQLite schema init | To build |
| frontend/package.json + src/App.jsx | To build |
| classifier/rules.json (hardcoded MVP) | To build |
| README.md | To build |

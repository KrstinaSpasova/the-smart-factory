# Smart Factory Operations Center

A multi-agent AI backend that analyses IPC (Industrial PC) sensor data from pizza production lines across Europe, classifies fleet health, and guides operators through data-driven right-sizing decisions — always with human approval before anything is persisted.

---

## Quick Start

### Prerequisites

- Docker Desktop (running)
- An Azure OpenAI API key and endpoint

### Setup

```bash
cp .env.example .env
# Fill in your Azure OpenAI credentials (see Environment Variables below)

docker compose up --build
```

| Service | URL |
|---|---|
| Chat UI (Streamlit) | http://localhost:8501 |
| API + interactive docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the required values:

```env
# Required — Azure OpenAI
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://....openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=group1-gpt-4.1
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# Optional — LangFuse tracing (leave as placeholders to disable)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Optional — override default ports
BACKEND_PORT=8000
FRONTEND_PORT=8501

# Optional — override data paths (defaults work inside Docker)
SENSOR_DATA_PATH=/app/data/sensor_data.csv
DATABASE_PATH=/app/data/memory.db
```

---

## Architecture

```
Operator (browser)
    │
    ▼
Streamlit UI  ──POST /chat──►  FastAPI backend
                                    │
                                    ▼
                             Orchestrator Agent
                             (LangGraph ReAct, Azure GPT-4.1)
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                   Fleet Analyst         Memory Manager
                  (read-only tools)     (SQLite decisions)
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        sensor_tools  classifier  memory_tools
        (pandas/CSV)  (thresholds) (SQLite)
```

### Agent layer

| Agent | Role |
|---|---|
| **Orchestrator** | Sole interface to the operator. Routes queries, enforces HITL, calls `save_decision` only after explicit approval. |
| **Fleet Analyst** | Read-only sub-agent. Loads sensor data, computes stats, classifies IPCs. Never writes anything. |
| **Memory Manager** | Thin wrapper around SQLite tools. Persists approved decisions and surfaces past history into the system prompt. |

### Human-in-the-Loop (HITL)

The Orchestrator never persists a decision without an explicit affirmative from the operator. It recognises natural-language approval:

- **Approve:** "yes", "approve", "go ahead", "do it", "confirm"
- **Reject:** "no", "reject", "skip", "don't", "not now"
- **Ambiguous:** anything else → asks for clarification before saving

---

## Data

**Source:** `data/sensor_data.csv` — 220,294 rows of daily CPU usage from 4,261 IPCs across 5 factories (May–June 2021).

**Key columns:** `IPC`, `Data Factory`, `time`, `AvgValue` (MHz), `CpuMHz` (rated clock)

**Derived feature:** `cpu_pct = AvgValue / CpuMHz * 100` — normalised utilisation percentage. Readings above 100% (known hardware anomalies) are dropped at load time.

---

## Classifier

The MVP uses hardcoded thresholds on `cpu_p95` (95th percentile of daily utilisation):

| cpu_p95 | Label | Suggested action |
|---|---|---|
| < 30% | `underutilized` | Downgrade at next maintenance window |
| 30–65% | `healthy` | No action required |
| 65–85% | `at_risk` | Schedule inspection; monitor closely |
| ≥ 85% | `overloaded` | Urgent hardware review or workload redistribution |

Current fleet breakdown (4,251 IPCs):

| Label | Count |
|---|---|
| underutilized | 3,923 |
| healthy | 264 |
| at_risk | 44 |
| overloaded | 20 |

---

## Starter prompts

```
Give me an overview of the fleet
Which IPCs are most at risk right now?
Show me the history for ITLT4301 over the last 30 days
What would you recommend for underutilized IPCs?
Are there any IPCs we should act on urgently?
```

---

## API Reference

### `POST /chat`

Send a natural-language message to the Orchestrator.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "operator-001", "message": "Which IPCs are most at risk?"}'
```

```json
{
  "reply": "I found 3 IPCs classified as at_risk or overloaded...",
  "session_id": "operator-001",
  "trace_id": "2bfd571724a7af32c1b349590ecd2fb7"
}
```

### `GET /fleet/summary`

Fleet-wide classification counts.

```json
{
  "total_ipcs": 4251,
  "count_per_label": {"underutilized": 3923, "healthy": 264, "at_risk": 44, "overloaded": 20},
  "factory_breakdown": {"1": 1063, "2": 842, "3": 1183, "4": 676, "5": 497}
}
```

### `GET /ipc/{ipc_id}/history?days=30`

Daily CPU utilisation time-series for one IPC.

```json
{
  "ipc_id": "ITLT4301",
  "records": [
    {"date": "2021-05-01", "cpu_pct": 87.3},
    {"date": "2021-05-02", "cpu_pct": 91.1}
  ]
}
```

### `GET /decisions`

All operator decisions persisted to SQLite.

```json
[
  {
    "id": 1,
    "ipc_id": "ITLT4301",
    "action": "Urgent hardware review",
    "rationale": "cpu_p95 = 91%",
    "status": "approved",
    "operator_note": null,
    "created_at": "2026-05-07T14:32:00"
  }
]
```

Full interactive docs at `http://localhost:8000/docs`.

---

## Project Structure

```
the-smart-factory/
├── docker-compose.yml
├── .env.example
├── data/
│   ├── sensor_data.csv          # Raw IPC sensor data (mounted read-only into backend)
│   └── memory.db                # SQLite decisions database (auto-created, gitignored)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI app — /chat, /fleet/summary, /ipc/…, /decisions
│       ├── agents/
│       │   ├── orchestrator.py  # Entry-point agent; HITL enforcement
│       │   ├── fleet_analyst.py # Read-only analysis sub-agent
│       │   └── memory_manager.py
│       ├── tools/
│       │   ├── sensor_tools.py      # CSV loading, utilisation stats, fleet summary
│       │   ├── classifier_tools.py  # Threshold-based IPC classification
│       │   └── memory_tools.py      # SQLite read/write
│       └── classifier/
│           └── rules.json           # Threshold rules (JSON form of the classifier)
└── frontend/
    ├── Dockerfile
    └── app.py                   # Streamlit chat UI
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | LangChain + LangGraph (`create_react_agent`) |
| LLM | Azure OpenAI GPT-4.1 (`langchain-openai`) |
| Observability | LangFuse (optional; traces each agent invocation) |
| Data analysis | pandas — vectorised CSV loading and aggregation |
| Persistence | SQLite (standard library `sqlite3`) |
| Backend API | FastAPI + uvicorn |
| Frontend | Streamlit |
| Containerisation | Docker + docker-compose |

---

## Example Conversation

```
Operator: Which IPCs should I be worried about?

Agent:    I found 2 IPCs needing attention:

          1. ITLT4301 (Factory 3) — OVERLOADED
             CPU p95: 91%
             Recommendation: Urgent hardware review or workload redistribution

          2. ITLT2034 (Factory 1) — UNDERUTILIZED
             CPU p95: 22%
             Recommendation: Downgrade at next maintenance window

          Would you like to approve, reject, or adjust these recommendations?

Operator: Approve ITLT4301. Reject ITLT2034 — new line next month.

Agent:    Understood. ITLT4301 escalated for urgent review.
          ITLT2034 deferred — noted the upcoming deployment.
```

Both decisions are now persisted to SQLite and visible at `GET /decisions`.

---

## What's Left (Good & Best Tiers)

The MVP is fully working and demo-able end-to-end. The following improvements are defined but not yet implemented:

### Good tier

- **Data-mined classifier** — replace hardcoded thresholds with a k-means → decision-tree pipeline trained on the actual data distribution; export rules to `classifier/rules.json` (`backend/app/classifier/train_classifier.py` scaffold already exists)
- **Dedicated Recommendation Engine agent** — currently recommendation logic lives inline in the Orchestrator system prompt; promote it to a separate LangChain agent
- **Anomaly counts in `/fleet/summary`** — surface `flag_anomalies` output (IPCs with `cpu_p95 > 85%` or `days_observed < 10`) alongside label counts

### Best tier

- **Operator preference memory** — persist operator style (e.g. "always defer Factory 5") to the `preferences` SQLite table and inject into the system prompt at session start
- **Time-series visualisation** — Streamlit sidebar panel showing a sparkline for selected IPCs using `GET /ipc/{ipc_id}/history`
- **Agent response streaming** — stream tokens from the Orchestrator to the Streamlit UI instead of blocking until the full reply is ready
- **Fleet summary caching** — cache the vectorised `get_fleet_summary` result with a TTL so repeated requests skip the CSV scan

# Smart Factory Operations Center
## Assignment Documentation

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Solution Architecture](#3-solution-architecture)
4. [Agent Design](#4-agent-design)
5. [Data Pipeline & Classifier](#5-data-pipeline--classifier)
6. [Memory System](#6-memory-system)
7. [Human-in-the-Loop (HITL)](#7-human-in-the-loop-hitl)
8. [Observability with LangFuse](#8-observability-with-langfuse)
9. [Project Structure](#9-project-structure)
10. [Setup & Running](#10-setup--running)
11. [API Reference](#11-api-reference)
12. [Design Decisions & Trade-offs](#12-design-decisions--trade-offs)

---

## 1. Project Overview

Itility has deployed a large-scale computer vision system across pizza production lines throughout Europe. Each production line is equipped with an IPC (Industrial PC) running image recognition software that monitors cheese distribution in real time.

With hundreds of IPCs spread across multiple factories generating sensor data every day, the operations team faces a growing challenge: identifying which IPCs are underutilized, which are at risk of overload, and what concrete actions should be taken to right-size the hardware fleet.

This project delivers an **Agentic AI Operations Center**: a multi-agent system powered by LangChain that analyzes IPC sensor data, reasons about fleet health, and guides operators through data-driven decisions — always with human approval before any action is recorded.

---

## 2. Problem Statement

During the initial rollout, high-capacity IPCs were purchased to guarantee stability. Now that the system has proven itself, the goal is to right-size the hardware fleet based on actual usage patterns — not guesswork.

### Key Questions the System Answers

- Which IPCs are consistently underutilized and candidates for downgrade?
- Which IPCs are approaching dangerous utilization levels and need intervention?
- Which IPCs are healthy and require no action?
- What does historical utilization look like for a specific IPC?
- What right-sizing actions should be prioritized across the fleet?

### Constraints

- All recommendations must be reviewed and approved by a human operator before being persisted
- Approved decisions and operator preferences must influence future recommendations
- Every agent call, tool call, and LLM call must be traceable via LangFuse
- No external database services — SQLite only

---

## 3. Solution Architecture

The system is built as a **multi-agent LangChain backend** with a lightweight chat frontend. Agents communicate through a central Orchestrator that manages conversation state and enforces the human-in-the-loop requirement.

```
Operator (chat interface)
        │
        ▼
┌─────────────────────┐
│   Orchestrator       │  ← manages conversation, routes requests, enforces HITL
└──────┬──────┬───────┘
       │      │         │
       ▼      ▼         ▼
  Fleet    Recommendation  Memory
  Analyst   Engine         Manager
       │      │         │
       ▼      ▼         ▼
  [CSV     [rules.json  [SQLite
  tools]    tools]      tools]
```

### Technology Stack

| Layer | Technology |
|---|---|
| Agent framework | LangChain |
| LLM | OpenAI GPT-4o (configurable) |
| Observability | LangFuse |
| Data analysis | pandas, scikit-learn |
| Persistence | SQLite (file-based) |
| Backend API | FastAPI + uvicorn |
| Frontend | React (Vite) or plain HTML/JS |
| Containerization | Docker + docker-compose |

---

## 4. Agent Design

### 4.1 Orchestrator Agent

**Role:** The sole entry point from the chat interface. Routes operator messages to the appropriate specialist agent, surfaces recommendations for human review, and enforces the HITL requirement — no action is persisted without explicit operator approval.

**Responsibilities:**
- Holds the full conversation history via LangChain `ConversationBufferMemory`
- Loads long-term memory context (past decisions, operator preferences) at the start of each session
- Decides which specialist agent(s) to invoke based on the operator's query
- Formats agent outputs into clear, reviewable proposals for the operator
- Passes approved/rejected decisions to the Memory Manager for persistence
- Adapts tone and recommendations based on stored operator preferences

**System prompt excerpt:**
```
You are the Smart Factory Operations Center assistant. You help operators
make data-driven decisions about IPC fleet management.

You NEVER record or act on a recommendation without explicit operator approval.
When you have a recommendation, present it clearly with the supporting reasoning
and ask the operator to approve, reject, or adjust before proceeding.

Before making recommendations, load past decisions and operator preferences
from memory to avoid re-suggesting rejected actions.
```

---

### 4.2 Fleet Analyst Agent

**Role:** Read-only analysis of IPC sensor data. Describes what the data says — never recommends what to do.

**Responsibilities:**
- Loads and queries the sensor CSV dataset
- Computes statistical summaries per IPC and across the fleet
- Flags anomalies and outliers
- Classifies each IPC using the data-mined rule classifier
- Returns structured facts to the Orchestrator

**Tools:**

| Tool | Signature | Description |
|---|---|---|
| `load_sensor_data` | `(ipc_id=None)` | Load CSV into DataFrame, optionally filter to one IPC |
| `compute_utilization_stats` | `(ipc_id)` | Return mean, p50, p95, p99, max per metric (CPU, mem, temp) |
| `flag_anomalies` | `(ipc_id=None)` | Detect IPCs with sustained highs, spikes, or abnormally low utilization |
| `get_fleet_summary` | `()` | Roll-up: total IPCs, count per classification bucket, top problem factories |
| `get_ipc_history` | `(ipc_id, days=30)` | Return time-series readings for a specific IPC over a time window |
| `classify_ipc` | `(ipc_id)` | Run data-mined rules → return label + rule that fired |

**Design principle:** The Fleet Analyst only describes what *is*. It has no knowledge of what actions should be taken. This keeps the agent's output fully auditable.

---

### 4.3 Recommendation Engine Agent

**Role:** Receives Fleet Analyst output and proposes concrete, prioritized actions. Does not access the database directly — it reasons from structured facts.

**Responsibilities:**
- Scores IPCs by urgency based on classification and utilization trends
- Generates human-readable right-sizing proposals with supporting rationale
- Ranks recommendations by priority (overloaded > at-risk > underutilized)
- Checks stored past decisions before proposing (avoids re-suggesting rejected actions)

**Tools:**

| Tool | Signature | Description |
|---|---|---|
| `score_ipc_urgency` | `(ipc_id, classification, stats)` | Produce a 0–100 urgency score based on classification and trend |
| `generate_rightsizing_plan` | `(ipc_id, classification, stats)` | Produce a structured proposal: action, rationale, expected impact |
| `rank_fleet_by_priority` | `(classifications_dict)` | Return ordered list of IPCs by urgency score |
| `check_past_decisions` | `(ipc_id)` | Query SQLite for prior decisions on this IPC to avoid repetition |

---

### 4.4 Memory Manager Agent

**Role:** All reads and writes to the SQLite long-term memory store. Acts as the persistence layer for the system.

**Responsibilities:**
- Save approved or rejected operator decisions with metadata
- Load past decisions to inform future recommendations
- Store and retrieve operator preferences (e.g. "always flag temperature before CPU")
- Provide context summaries to the Orchestrator at session start

**Tools:**

| Tool | Signature | Description |
|---|---|---|
| `save_decision` | `(ipc_id, action, rationale, status, operator_note=None)` | Persist an approved or rejected recommendation |
| `load_past_decisions` | `(ipc_id=None)` | Retrieve stored decisions, optionally filtered to one IPC |
| `save_operator_preference` | `(key, value)` | Store a named operator preference |
| `load_operator_preferences` | `()` | Return all stored operator preferences as a dict |
| `get_session_context` | `()` | Return a summary of recent decisions for Orchestrator context injection |

---

## 5. Data Pipeline & Classifier

Rather than hardcoding utilization thresholds, the system derives them from the actual fleet data. This produces defensible, data-grounded rules that can be shown to and verified by Itility.

### 5.1 Pipeline Stages

**Stage 1 — Exploratory Data Analysis**

Run before building anything else. Goals:
- Understand feature distributions (CPU %, memory %, temperature, uptime, error rate)
- Identify outliers and missing values
- Check feature correlations (highly correlated features can distort clustering)
- Establish baseline statistics per IPC and per factory

Tools: `pandas`, `matplotlib`, `seaborn`. Output: EDA report + feature selection decision.

**Stage 2 — Unsupervised Clustering**

Cluster all IPCs in feature space using normalized sensor metrics. Each IPC is represented as a vector of its p95 CPU, p95 memory, mean temperature, and mean uptime.

- Primary algorithm: **k-means** (k=4 targeting four natural groups)
- Validation: **DBSCAN** to cross-check and catch irregular clusters / outliers
- Normalization: `StandardScaler` before clustering to prevent any one metric dominating

**Stage 3 — Cluster Characterization**

Inspect cluster centroids and assign human-meaningful labels:

| Label | Typical centroid characteristics |
|---|---|
| `healthy` | Moderate CPU (30–65%), stable memory, normal temperature |
| `underutilized` | Low CPU (<30%), low memory, low temperature, long uptime |
| `at_risk` | Elevated p95 CPU (65–85%), rising temperature trend |
| `overloaded` | Very high p95 CPU (>85%), high temperature, possible errors |

This labeling step is the one human judgment call in the pipeline and should be reviewed with domain experts.

**Stage 4 — Decision Tree Distillation**

Fit a shallow `DecisionTreeClassifier` (max depth 4) on the cluster-labeled dataset. Export human-readable rules using `sklearn.tree.export_text()`.

Example output:
```
IF cpu_p95 <= 42.3% AND mem_avg <= 38.1%
    → underutilized

IF cpu_p95 > 42.3% AND cpu_p95 <= 84.7% AND temp_mean <= 71.2°C
    → healthy

IF cpu_p95 > 84.7% OR temp_mean > 71.2°C
    → overloaded
```

These rules are saved to `rules.json` and loaded by the `classify_ipc` tool at runtime.

**Stage 5 — Rule Encoder as LangChain Tool**

The `classify_ipc(ipc_id)` tool:
1. Loads the IPC's stats via `compute_utilization_stats`
2. Evaluates the rules from `rules.json` in order
3. Returns `{"label": "underutilized", "rule_fired": "cpu_p95 <= 42.3% AND mem_avg <= 38.1%", "confidence": 0.91}`

The returned `rule_fired` field is surfaced to the operator alongside every recommendation, making the system fully explainable.

---

## 6. Memory System

### 6.1 Short-term Memory

Implemented using LangChain's `ConversationBufferMemory`. Stores the full message history of the current session. Passed as context to the Orchestrator on every turn so the agent remembers what was discussed, what was approved, and what was rejected within the session.

### 6.2 Long-term Memory

File-based SQLite database at `data/memory.db`. Created automatically on first run.

**Schema:**

```sql
CREATE TABLE decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ipc_id      TEXT NOT NULL,
    action      TEXT NOT NULL,
    rationale   TEXT,
    status      TEXT NOT NULL,   -- 'approved' | 'rejected' | 'deferred'
    operator_note TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE preferences (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**How long-term memory influences recommendations:**

At the start of each session, the Orchestrator calls `get_session_context()` which returns a summary of the last N decisions. This is injected into the system prompt. Before the Recommendation Engine proposes an action on any IPC, `check_past_decisions(ipc_id)` is called — if a prior rejection exists, the agent either skips that IPC or explicitly acknowledges the prior decision and explains why it is re-raising it (e.g. the situation has materially worsened).

---

## 7. Human-in-the-Loop (HITL)

The HITL requirement is enforced architecturally, not just by instruction. The Orchestrator is the only agent that communicates with the operator, and it never calls `save_decision` without an explicit affirmative response.

### HITL Conversation Flow

```
Operator:      "Which IPCs should I be worried about?"

Orchestrator:  [calls Fleet Analyst → get_fleet_summary, flag_anomalies]
               [calls Recommendation Engine → rank_fleet_by_priority]

               "I found 3 IPCs needing attention:

               1. IPC-042 (Factory Eindhoven, Line 3) — OVERLOADED
                  CPU p95: 91%, Temperature: 74°C
                  Recommendation: Urgent hardware review or workload redistribution
                  Rule fired: cpu_p95 > 84.7% OR temp_mean > 71.2°C

               2. IPC-107 (Factory Amsterdam, Line 1) — UNDERUTILIZED
                  CPU p95: 28%, Memory avg: 31%
                  Recommendation: Downgrade to next tier hardware at next maintenance window
                  Rule fired: cpu_p95 <= 42.3% AND mem_avg <= 38.1%

               Would you like to approve, reject, or adjust these recommendations?"

Operator:      "Approve IPC-042. Reject IPC-107 — it's being used for a new line next month."

Orchestrator:  [calls Memory Manager → save_decision(ipc_id='IPC-042', status='approved')]
               [calls Memory Manager → save_decision(ipc_id='IPC-107', status='rejected',
                                        operator_note='new line deployment next month')]

               "Understood. IPC-042 escalated for urgent review. IPC-107 deferred —
               I've noted the upcoming deployment and will not re-raise it until
               you indicate the new line is live."
```

### What Counts as Approval

The system recognizes natural language approval: "yes", "approve", "go ahead", "do it", "confirm", and variants. Ambiguous responses ("maybe", "I'll think about it") prompt the Orchestrator to ask for clarification before saving anything.

---

## 8. Observability with LangFuse

Every agent call, tool call, and LLM call is traced in LangFuse.

### Trace Structure

```
Trace: user_session_{session_id}
  └── Span: orchestrator.run
        ├── Generation: orchestrator.llm_call
        ├── Span: fleet_analyst.run
        │     ├── Event: tool.get_fleet_summary
        │     ├── Event: tool.flag_anomalies
        │     └── Event: tool.classify_ipc (× N)
        ├── Span: recommendation_engine.run
        │     ├── Event: tool.check_past_decisions (× N)
        │     ├── Event: tool.score_ipc_urgency (× N)
        │     └── Event: tool.generate_rightsizing_plan (× N)
        └── Span: memory_manager.run [if HITL approved]
              └── Event: tool.save_decision
```

### Configuration

Set in `.env`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

LangFuse callbacks are registered on the LangChain `callbacks` parameter at the agent level, so all child calls are automatically captured without manual instrumentation of each tool.

---

## 9. Project Structure

```
smart-factory-ops/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI app, /chat endpoint
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── fleet_analyst.py
│   │   ├── recommendation_engine.py
│   │   └── memory_manager.py
│   ├── tools/
│   │   ├── sensor_tools.py      # load_sensor_data, compute_utilization_stats, etc.
│   │   ├── classifier_tools.py  # classify_ipc, flag_anomalies
│   │   ├── recommendation_tools.py
│   │   └── memory_tools.py
│   ├── classifier/
│   │   ├── eda.ipynb            # exploratory analysis notebook
│   │   ├── train_classifier.py  # clustering → decision tree → rules.json
│   │   └── rules.json           # exported IF/THEN rules (generated, committed)
│   └── data/
│       └── sensor_data.csv      # provided IPC sensor dataset
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       └── App.jsx              # chat interface
├── data/                        # Docker volume mount point
│   └── memory.db                # auto-created SQLite (gitignored)
├── docker-compose.yml
├── .env.example
├── README.md
└── ASSIGNMENT.md
```

---

## 10. Setup & Running

### Prerequisites

- Docker and docker-compose installed
- An OpenAI API key
- A LangFuse account (free tier is sufficient) or self-hosted LangFuse instance

### Steps

**1. Clone and configure**

```bash
git clone <repo-url>
cd smart-factory-ops
cp .env.example .env
# Edit .env and fill in your keys
```

**2. `.env` values to fill in**

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

DATABASE_PATH=/app/data/memory.db
SENSOR_DATA_PATH=/app/backend/data/sensor_data.csv
```

**3. (Optional) Re-run the classifier training**

If you want to regenerate `rules.json` from the sensor data:

```bash
cd backend
pip install -r requirements.txt
python classifier/train_classifier.py
```

This is not required — a pre-generated `rules.json` is committed to the repository.

**4. Start the stack**

```bash
docker-compose up --build
```

**5. Open the chat interface**

Navigate to `http://localhost:3000` in your browser.

The backend API is available at `http://localhost:8000`. The interactive API docs are at `http://localhost:8000/docs`.

### Useful starter prompts

```
"Give me an overview of the fleet"
"Which IPCs are most at risk right now?"
"Show me the history for IPC-042 over the last 30 days"
"What would you recommend we do about underutilized IPCs?"
"Are there any IPCs we should act on urgently?"
```

---

## 11. API Reference

### `POST /chat`

Send a message to the Orchestrator and receive a response.

**Request:**
```json
{
  "session_id": "operator-session-001",
  "message": "Which IPCs are underutilized?"
}
```

**Response:**
```json
{
  "session_id": "operator-session-001",
  "response": "I found 12 IPCs classified as underutilized across 3 factories...",
  "agent_trace_id": "trace-abc123"
}
```

### `GET /fleet/summary`

Returns the current fleet classification summary without going through the chat agent. Useful for dashboard integration.

### `GET /ipc/{ipc_id}/history`

Returns raw time-series data for a specific IPC.

### `GET /decisions`

Returns all stored decisions from the long-term memory store.

---

## 12. Design Decisions & Trade-offs

### Why four agents instead of one?

A single monolithic agent could technically handle all tasks, but separating concerns gives three concrete benefits: (1) each agent's system prompt is focused and short, reducing prompt confusion; (2) the Fleet Analyst can be called independently for pure data queries without triggering the recommendation flow; (3) when something goes wrong in LangFuse traces, the failure is immediately localized to one agent.

### Why data-mined rules instead of hardcoded thresholds?

Hardcoded thresholds (e.g. "CPU > 80% = overloaded") are arbitrary and not grounded in the actual behavior of this specific fleet. By clustering the data and distilling a decision tree, the thresholds emerge from what the IPCs actually do. The rules are also fully explainable — every recommendation surfaces the exact rule that fired, which builds operator trust and makes the system auditable.

### Why a decision tree over the raw cluster labels?

Cluster labels alone would require rerunning k-means on every classification request, which is slow and non-deterministic. The decision tree distillation step converts the cluster findings into a fast, deterministic, and human-readable ruleset that runs in microseconds at inference time.

### Why SQLite for long-term memory?

The assignment specifies no external database services. SQLite is file-based, ships in Python's standard library, requires zero configuration, and persists correctly via a Docker volume mount. For a fleet of hundreds of IPCs with modest decision history, it is more than sufficient.

### Trade-off: `ConversationBufferMemory` vs `ConversationSummaryMemory`

`ConversationBufferMemory` keeps the full history in the context window, which is accurate but gets expensive over long sessions. For a production system with very long sessions, `ConversationSummaryMemory` would periodically compress history into a summary. For this assignment, the full buffer is the right call — it's simpler, more predictable, and the session length is bounded.

### Why FastAPI over Flask?

FastAPI gives automatic OpenAPI docs at `/docs`, async support (useful if multiple operators are using the system simultaneously), and Pydantic request validation with minimal boilerplate. The `/docs` endpoint also makes it easy for the graders to explore the API during the demo.

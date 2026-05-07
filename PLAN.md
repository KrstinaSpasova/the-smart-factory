# Smart Factory Operations Center — Build Plan

---

## Stack

| Layer | Choice |
|---|---|
| Frontend | **Streamlit** (`st.chat_message` + `st.chat_input`) |
| Agent framework | **LangGraph** (supervisor pattern) |
| LLM | Provided API key |
| Classifier | **KMeans → DecisionTreeClassifier** (sklearn), trained offline, loaded as pickle at runtime |
| Short-term memory | LangGraph `MessagesState` + Streamlit `session_state` |
| Long-term memory | **SQLite** — `decisions` + `preferences` tables |
| Observability | **LangFuse Cloud** (free tier) |
| Packaging | **Docker Compose** — 1 app service + 1 SQLite volume |

---

## Repo structure

```
smart-factory-ops/
├── analysis/
│   └── train_classifier.py     # Run once offline — produces model artifacts
├── artifacts/
│   ├── scaler.pkl              # StandardScaler fitted on fleet features
│   ├── classifier.pkl          # DecisionTreeClassifier (max_depth=3)
│   ├── cluster_labels.json     # {0: "underutilized", 1: "healthy", ...}
│   └── tree_rules.txt          # Human-readable IF/THEN rules (use in demo)
├── data/
│   └── ipc_sensor_data.csv     # Provided dataset (semicolon-delimited)
├── memory/
│   └── operations.db           # SQLite file (auto-created on first run)
├── tools.py                    # All @tool functions used by agents
├── agent.py                    # LangGraph graph definition
├── prompts.py                  # System prompts for each agent node
├── db.py                       # SQLite schema + helper functions
├── app.py                      # Streamlit chat interface
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env                        # API keys (not committed)
├── .env.example
└── README.md
```

---

## Data format

Semicolon-delimited CSV, ~22,000 rows, **long format** (one row per IPC per day per metric).

```
Columns: IPC | Data Factory | time | AvgValue | MinValue | MaxValue | MetricId | CpuMHz
Example: ITLT4301 | 1 | 01/05/2021 | 98 | ... | CpuUsageMHz | 5600
```

Load with `pd.read_csv('data/ipc_sensor_data.csv', sep=';')`.

**First thing:** run `df['MetricId'].unique()` — everything in the clustering pipeline depends on those exact string values.

CPU utilization % = `AvgValue / CpuMHz * 100`

---

## Architecture

```
Chat interface (Streamlit)
        │
        ▼
┌─────────────────────────────────────┐
│         Orchestrator agent          │
│  Routes · manages conv · gates HITL │
└──────┬──────────────┬───────────────┘
       │              │
┌──────▼──────┐ ┌─────▼────────────┐ ┌──────────────────┐
│   Fleet     │ │  Recommendation  │ │     Memory       │
│   Analyst   │ │  Engine          │ │     Manager      │
└──────┬──────┘ └─────┬────────────┘ └──────────┬───────┘
       │              │                          │
load_sensor_csv  score_ipc_utilization     save_decision
compute_fleet_stats (← classifier.pkl)    load_past_decisions
flag_anomalies   generate_rightsizing_plan load_operator_prefs
                 rank_by_priority                │
                                                 ▼
                                       SQLite (decisions · preferences)
```

**Key decisions:**
- Orchestrator never touches data. Analyst never recommends. Recommender never writes memory.
- Classifier is trained once offline. At runtime the agent only loads the pickle — no ML at query time.
- `tree_rules.txt` is the demo differentiator: explainable, data-driven thresholds.

---

## Build roadmap

### Step 1 — Explore the data
Open the CSV. Run `df['MetricId'].unique()`, check for nulls, understand the IPC count and date range. Nothing else starts until you know what metrics exist.

### Step 2 — Train the classifier (`analysis/train_classifier.py`)
1. Load CSV, pivot to one row per IPC, compute features:
   `cpu_avg`, `cpu_p95`, `mem_avg`, `mem_p95`, `temp_mean`, `temp_max`
2. `StandardScaler` → `KMeans(n_clusters=4)`, inspect centroids
3. Hand-label clusters by centroid values: `underutilized / healthy / at-risk / overloaded`
4. Train `DecisionTreeClassifier(max_depth=3)` on features → label
5. `export_text(tree)` → save to `artifacts/tree_rules.txt`
6. Save `scaler.pkl`, `classifier.pkl`, `cluster_labels.json` to `artifacts/`

> **Gut check:** clusters must separate cleanly and label intuitively.
> If not → fall back to **percentile thresholds** (bottom quartile = underutilized, top = at-risk). Same tool interface, zero agent changes.

### Step 3 — Build the tools (`tools.py`)

```python
# Fleet Analyst tools
load_sensor_csv() -> pd.DataFrame
compute_fleet_stats() -> dict
flag_anomalies() -> list[str]

# Recommendation Engine tools
score_ipc_utilization(ipc_id: str) -> dict    # calls classifier.pkl
generate_rightsizing_plan(ipc_id: str) -> dict
rank_by_priority(ipc_ids: list[str]) -> list[dict]

# Memory Manager tools
save_decision(ipc_id, action, status, reason) -> bool
load_past_decisions(ipc_id: str) -> list[dict]
load_operator_prefs() -> dict
```

### Step 4 — Set up the database (`db.py`)

```sql
CREATE TABLE IF NOT EXISTS decisions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ipc_id    TEXT NOT NULL,
    action    TEXT NOT NULL,
    status    TEXT NOT NULL,   -- approved | rejected | deferred
    reason    TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Step 5 — Build the agents (`agent.py`)
- `StateGraph` with `MessagesState`
- Supervisor routes to Analyst, Recommender, or Memory Manager based on user intent
- `interrupt_before` on Recommender → Supervisor edge to enforce HITL
- LangFuse `CallbackHandler` registered on the graph

### Step 6 — Write the prompts (`prompts.py`)
One system prompt per agent node. Each must specify:
- What it owns (and what it does NOT do)
- Which tools to call and when
- Orchestrator prompt must explicitly say: always present recommendations before acting, always wait for operator approval

### Step 7 — Build the chat interface (`app.py`)
- `st.chat_input` → feeds into the LangGraph graph
- `st.chat_message` → renders the conversation
- `st.session_state` → holds message history (short-term memory)
- On startup: load past decisions + operator preferences, inject into initial system context

### Step 8 — Docker + environment

```yaml
# docker-compose.yml
services:
  app:
    build: .
    ports: ["8501:8501"]
    volumes:
      - ./memory:/app/memory
      - ./artifacts:/app/artifacts
      - ./data:/app/data
    env_file: .env
```

`.env.example`:
```
ANTHROPIC_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## HITL flow (validate this end-to-end before polishing anything else)

1. Operator: *"Which IPCs are over-provisioned?"*
2. Analyst runs → Recommender proposes actions → Orchestrator **pauses and presents to operator**
3. Operator: *"Approve IPC-042, defer IPC-107 — new line launches next month"*
4. Memory Manager writes both decisions to SQLite
5. New conversation, same question → agent loads past decisions → does not re-suggest IPC-107

---

## Fallback plan

| Risk | Fallback |
|---|---|
| Clusters don't separate cleanly | Percentile thresholds — same tool interface, no agent changes |
| LangGraph HITL too complex | Agent outputs `[NEEDS_APPROVAL]` prefix, Streamlit holds until user responds |
| Docker time runs out | Demo locally, submit compose file anyway |

---

## Demo script (8 min)

1. Architecture diagram — 4 agents, who owns what and why
2. Show `tree_rules.txt` — "the data defined the thresholds, not us"
3. Live: broad question → recommendation → approve one, defer one with reason → new conversation → agent references the deferral
4. Click LangFuse — show the trace for the last turn
5. Trade-offs: Streamlit, offline classifier, 4 agents, SQLite, LangFuse Cloud
6. What we'd add with one more day

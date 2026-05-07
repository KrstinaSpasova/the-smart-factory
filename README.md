# Smart Factory Operations Center

A multi-agent AI system that analyzes IPC sensor data from pizza production lines, reasons about fleet health, and guides operators through right-sizing decisions — always with human approval before any action is recorded.

---

## Prerequisites

- Docker and Docker Compose
- A Groq API key (free tier at console.groq.com)
- A LangFuse account (free tier at cloud.langfuse.com) — optional but recommended for tracing

---

## Setup

**1. Clone and configure**

```bash
git clone <repo-url>
cd the-smart-factory
cp .env.example .env
```

**2. Fill in `.env`**

```env
GROQ_API_KEY=gsk_...          # required
GROQ_MODEL=llama-3.3-70b-versatile

LANGFUSE_PUBLIC_KEY=pk-lf-... # optional — leave placeholder to disable tracing
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

**3. Place the sensor data**

Copy the CSV file into the `data/` directory (create it if it doesn't exist):

```bash
mkdir -p data
cp "Database - Testcase_agentic_ai_V1.0.zip.csv" data/
```

**4. Start the stack**

```bash
docker compose up --build
```

Both services build and start. The backend may take ~30 seconds on first run while pandas loads the CSV.

---

## URLs

| Service | URL |
|---|---|
| Chat UI (Streamlit) | http://localhost:8501 |
| API + interactive docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

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

## Agent design

The system uses three agents wired through a central Orchestrator:

- **Orchestrator** — sole interface to the chat UI; routes messages, enforces the human-in-the-loop requirement, and injects past decisions into context at session start
- **Fleet Analyst** — read-only; loads and queries the sensor CSV, classifies each IPC, flags anomalies
- **Memory Manager** — all SQLite reads/writes; only called after the operator explicitly approves a recommendation

No action is ever saved without an affirmative response from the operator.

---

## Project structure

```
backend/app/
├── main.py                  # FastAPI — /chat, /fleet/summary, /ipc/{id}/history, /decisions
├── agents/
│   ├── orchestrator.py      # Entry point; HITL enforcement; ConversationBufferMemory
│   ├── fleet_analyst.py     # Sensor analysis sub-agent
│   └── memory_manager.py    # SQLite persistence wrapper
└── tools/
    ├── sensor_tools.py      # load_sensor_data, compute_utilization_stats, …
    ├── classifier_tools.py  # classify_ipc, flag_anomalies
    └── memory_tools.py      # save_decision, load_past_decisions, get_session_context

frontend/
└── app.py                   # Streamlit chat UI

data/
└── memory.db                # Auto-created SQLite (Docker volume, gitignored)
```

---

## Re-running the classifier (optional)

The committed `rules.json` is ready to use. To regenerate from the data:

```bash
cd backend
pip install -r requirements.txt scikit-learn
python app/classifier/train_classifier.py
```

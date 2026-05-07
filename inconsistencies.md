# Architecture Inconsistencies

Validated against: `PLAN.md`, `ARCHITECTURE.md`, `PRIORITIES.md`, `ASSIGNMENT.md`, `docker-compose.yml`, `requirements.txt`, `.env.example`, `frontend/Dockerfile`.

---

## What's Consistent

| Area | Status |
|---|---|
| FastAPI backend, Python 3.11, uvicorn | All docs + Dockerfile agree |
| LangChain + `langchain-anthropic` | requirements.txt matches ARCHITECTURE.md |
| LangFuse observability | requirements.txt + .env.example match all docs |
| SQLite for long-term memory | ARCHITECTURE.md and ASSIGNMENT.md agree |
| Four-agent design (Orchestrator, Fleet Analyst, Recommendation Engine, Memory Manager) | ARCHITECTURE.md and ASSIGNMENT.md agree |
| Hardcoded thresholds for MVP classifier | PRIORITIES.md + ARCHITECTURE.md agree |
| HITL flow | Consistent across all docs |

---

## Inconsistencies

### 1. Frontend framework — Node/React vs Streamlit

- `PLAN.md` says Streamlit
- `docker-compose.yml` + `frontend/Dockerfile` use `node:20-alpine` with `npm start`
- `ARCHITECTURE.md` says React 18 + Vite

**Resolution:** React is the decided choice — Dockerfile and compose are ground truth. PLAN.md is outdated. The `frontend/` directory still needs `package.json` and source files scaffolded.

---

### 2. Agent framework — LangChain vs LangGraph

- `PLAN.md` says LangGraph
- `requirements.txt` has `langchain` + `langchain-anthropic` — no `langgraph`
- `PRIORITIES.md` places LangGraph in the "Best" tier

**Resolution:** Plain LangChain targets MVP. LangGraph is a known future upgrade. Do not add `langgraph` to requirements.txt until reaching that tier.

---

### 3. Row count — PLAN.md is off by 10x

- `PLAN.md` says ~22,000 rows
- Actual EDA (v2–v5): **220,294 rows**

Any hardcoded limits, batch sizes, or performance assumptions in PLAN.md based on ~22k rows should be revisited.

---

### 4. Missing `data/` directory — Docker mount is broken (blocker)

- `docker-compose.yml` mounts `./data:/app/data:ro`
- No `the-smart-factory/data/` directory exists — the CSV sits loose in `the-smart-factory/` root

The container will mount an empty or non-existent path, causing the backend to start with no data.

**Fix:** Create `the-smart-factory/data/` and move or symlink the CSV into it, or update the mount source in `docker-compose.yml`.

---

### 5. LLM provider ambiguity in ASSIGNMENT.md

- `ASSIGNMENT.md` says "OpenAI/Anthropic"
- `.env.example` only has `ANTHROPIC_API_KEY` — no `OPENAI_API_KEY`
- `requirements.txt` has `langchain-anthropic`, not `langchain-openai`

**Resolution:** Anthropic is the decided provider. ASSIGNMENT.md was written before the provider was locked in. Ignore OpenAI references there.

---

### 6. CLAUDE.md incorrectly states the repo is not a git repo

- `CLAUDE.md`: *"The repo is not a git repository"*
- `the-smart-factory/` has a `.git/` directory — it is a git repo

The root assignment folder is not a git repo, but the deliverable subfolder is.

---

## Recommended Actions (priority order)

1. **Create `the-smart-factory/data/`** and place the CSV there — the Docker data mount is broken without it; this is the only hard blocker.
2. **Scaffold the React/Vite frontend** — `frontend/` needs `package.json` and source files before the container can build.
3. **Create `backend/app/main.py`** — the Dockerfile CMD references it; the backend crashes on start without it.
4. Treat PLAN.md's ~22k row count and Streamlit references as stale.

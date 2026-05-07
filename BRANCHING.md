# Branching Strategy

## Branch per person

```
master
├── feat/m-tools        ← M: data + tools layer
├── feat/k-agents       ← K: agent layer
└── feat/j-infra        ← J: infrastructure + frontend
```

Create with:

```bash
git checkout -b feat/m-tools
git checkout -b feat/k-agents
git checkout -b feat/j-infra
```

---

## Ownership map

| Branch | Files owned | Independent from day 1? |
|---|---|---|
| `feat/m-tools` | `backend/app/tools/`, `backend/app/classifier/` | Yes |
| `feat/k-agents` | `backend/app/agents/` | Partial — see dependencies |
| `feat/j-infra` | `backend/app/main.py`, `frontend/app.py`, `docker-compose.yml`, `.env.example`, `README.md` | Yes |

---

## What is fully independent

**M** — `feat/m-tools` has zero imports from the rest of the repo. Write and test in pure Python with no coordination needed.

**J** — `feat/j-infra` is isolated by design. `main.py` stubs return placeholder JSON; the Streamlit frontend calls `/chat` over HTTP. Neither imports K's or M's code.

---

## What has dependencies

**K** — `feat/k-agents` can be scaffolded independently (stub tool list, mock data), but wiring real tools in hour 2 requires M's `sensor_tools` and `memory_tools` to exist on `master` first.

Pattern:
```
K scaffolds agents with stubs
    ──► M merges feat/m-tools → master
         ──► K: git rebase master (gets real tools)
              ──► K wires tools into agents
```

---

## Merge order

```
T+1:00  M merges feat/m-tools → master
         K rebases feat/k-agents onto master

T+2:00  K merges feat/k-agents → master
         J rebases feat/j-infra onto master
         J replaces /chat stub with orchestrator.invoke(...)

T+3:00  J merges feat/j-infra → master
         → docker compose up --build
```

---

## The one file to coordinate on

`backend/app/main.py` is owned by J. K needs to know the `ChatRequest` / `ChatResponse` schema to write `orchestrator.invoke(...)` correctly. The schema is already defined — **K reads it, J owns it, neither edits it at the same time.**

Current schema (do not change without telling the team):

```python
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    reply: str
    session_id: str
```

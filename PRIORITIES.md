# Priorities

Tiered feature breakdown for the Smart Factory Operations Center. Build MVP first, then layer on Good, then Best if time allows.

---

## MVP — must-have to submit

- Chat interface (single page, send message + see reply)
- FastAPI backend with `/chat` endpoint
- Single-agent fallback OR Orchestrator + Fleet Analyst working
- Load sensor CSV into pandas
- Basic utilization stats tool (mean, p95 per IPC)
- Hardcoded threshold classifier (CPU/mem/temp cutoffs)
- Simple recommendation output in chat
- HITL: agent asks "approve?" before any "save"
- SQLite `decisions` table — save approved/rejected
- LangChain `ConversationBufferMemory` for short-term
- LangFuse callback registered on the agent
- `docker-compose.yml` with backend + frontend
- README with setup steps
- `.env.example` with all required keys

---

## Good — solid submission

- Full 4-agent architecture (Orchestrator, Fleet Analyst, Recommendation Engine, Memory Manager)
- Data-mined classifier: k-means clustering → decision tree → `rules.json`
- `classify_ipc` tool surfaces the rule that fired
- Anomaly detection tool (`flag_anomalies`)
- Fleet summary roll-up tool (`get_fleet_summary`)
- IPC history tool (`get_ipc_history`)
- `check_past_decisions` consulted before recommending
- Operator preferences table in SQLite + `save_operator_preference` tool
- Long-term memory injected into Orchestrator system prompt at session start
- Recommendations include urgency score and prioritized ranking
- LangFuse traces show nested spans per agent
- API documented at `/docs` (FastAPI auto-generated)
- EDA notebook committed for transparency
- ASSIGNMENT.md with architecture, agent design, trade-offs

---

## Best — stretch goals

- LangGraph for explicit agent state machine
- Multi-turn HITL adjustments ("approve but defer 30 days")
- Operator can ask "why?" and get the rule trace explained
- Trend analysis: detect IPCs degrading over time, not just snapshots
- Confidence score on each classification (distance to decision boundary)
- Auto-retraining pipeline: rerun classifier when new data arrives
- Per-factory and per-line breakdowns in fleet summary
- Operator profile system: different operators see different default views
- Conversation export (download session as markdown)
- Frontend: streaming responses, show agent thinking step-by-step
- Frontend: render recommendation cards with approve/reject buttons (still chat-driven underneath)
- LangFuse score evaluation: tag bad responses for quality tracking
- Test suite for tools (pytest on `compute_utilization_stats`, `classify_ipc`, etc.)
- Demo script: pre-loaded session showing full HITL + memory flow

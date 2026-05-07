# M's Plan — Data + Tools Layer

**Branch:** `m/data-tools-layer`
**Scope:** `backend/app/tools/` + `backend/app/classifier/` + the `data/` blocker fix
**Time budget:** 3 hours
**Strength match:** data science → pandas + SQLite work. No LangChain concepts touch your code.

---

## Context you must internalize before coding

### The dataset (read this first — saves debugging later)

CSV path on host: `C:\Users\tmiha\Documents\Touchpulse\Assignment\Database - Testcase_agentic_ai_V1.0.zip.csv`
Inside the container, after the blocker fix: `/app/data/sensor_data.csv`

**Format gotchas (from `eda_v4.py`):**

- European CSV: `sep=";"`, `decimal=","`, `dayfirst=True`. Naive `pd.read_csv(path)` produces a single-column garbage frame.
- Columns: `time, MetricId, IPC, Data Factory, CpuMHz, AvgValue, MinValue, MaxValue` (8 total).
- 220,294 rows · 4,261 unique IPCs · 5 factories · date range **2021-05-01 → 2021-06-30** (61 days).
- One IPC maps to exactly one `Data Factory` and one `CpuMHz` (verified in EDA v4).

**The CPU% calculation — non-obvious:**

- `CpuMHz` is the **rated** clock of the IPC's processor(s).
- `AvgValue` (with the right `MetricId`) is the **measured** MHz being consumed.
- Some `CpuMHz` cells are composite multi-CPU strings like `"2400 2400"` — take the first token:
  ```python
  df["CpuMHz_num"] = df["CpuMHz"].astype(str).str.split().str[0].astype(float)
  ```
- Then `cpu_pct = 100 * AvgValue / CpuMHz_num`. EDA v4 confirmed this column is sane (most values <50%, some outliers >100%).
- **Drop `cpu_pct > 100` as outliers** (per `TASK_SPLIT.md`).

### What ARCHITECTURE.md says (the binding spec)

- **§3 Data:** Columns + parsing convention.
- **§8 Tool catalogue:** Names and signatures of the tools you must produce.
- **§9 Classifier:** MVP = hardcoded thresholds on `cpu_p95`. Good tier (skip for MVP) = k-means + decision tree.
- **§10 Memory:** SQLite at `/app/data/memory.db`. Tables `decisions` and `preferences`.

### Thresholds (memorize these — they appear in two files)

| `cpu_p95` range | Label |
|---|---|
| `< 30` | `underutilized` |
| `30 ≤ x < 65` | `healthy` |
| `65 ≤ x < 85` | `at_risk` |
| `≥ 85` | `overloaded` |

### Environment variables you will read

```
SENSOR_DATA_PATH=/app/data/sensor_data.csv
DATABASE_PATH=/app/data/memory.db
```

Use `os.getenv("SENSOR_DATA_PATH", "/app/data/sensor_data.csv")` — never hardcode a host path inside the module. The same code must work in Docker and on the host during local smoke tests.

### Files you will write (all currently empty stubs)

```
the-smart-factory/
├── data/                                  # CREATE THIS — Hour 1, step 1
│   └── sensor_data.csv                    # COPY THE CSV HERE
└── backend/app/
    ├── tools/
    │   ├── sensor_tools.py                # Hour 1
    │   ├── classifier_tools.py            # Hour 2
    │   └── memory_tools.py                # Hour 2
    └── classifier/
        └── rules.json                     # Hour 2
```

### Files you must NOT touch

- `backend/app/agents/*` — that's K's surface.
- `backend/app/main.py`, `frontend/`, `docker-compose.yml`, `.env.example` — that's J's surface.
- `requirements.txt` — K already swapped LLM provider; if you need a new package, ping the team first. **Note:** the current `requirements.txt` lists `langchain-groq` (not `langchain-openai` as `TASK_SPLIT.md` says). Don't fix it — let K decide.

### Skills you have available that are actually useful here

- **`simplify`** — run this on each file when you finish it. Catches dead code, premature abstractions, and unused params. Use it instead of re-reading your own code.
- **None of the others apply.** Skip n8n/gitnexus/claude-api skills entirely — wrong domain.

### Vibe-coding ground rules (read once, then forget)

- **Never write `pd.read_csv(path)` without `sep=";", decimal=",", dayfirst=True`.** This bug already happened once (`eda_v1.py`) — that's why EDA scripts are versioned.
- **Cache the loaded dataframe** in a module-level variable. Reloading 220k rows on every tool call will make the agent feel sluggish during demo.
- **Functions return JSON-serializable dicts/lists**, not numpy types. `int(x)`, `float(x)` your numpy scalars before returning. LangChain serializes tool results to strings — `np.int64` will sometimes work, sometimes not. Cast defensively.
- **No print statements in tool modules.** They pollute the agent trace. Use `logging.getLogger(__name__)` if you must.
- **Pandas SettingWithCopyWarning is your enemy during demo.** When you filter then assign, use `.copy()` or `.loc[...]`.

---

## Hour 1 (T+0:00 → T+1:00)

### Step 1.1 — Unblock everyone (5 min, do this FIRST)

```powershell
# from C:\Users\tmiha\Documents\Touchpulse\Assignment\the-smart-factory
mkdir data
copy "..\Database - Testcase_agentic_ai_V1.0.zip.csv" "data\sensor_data.csv"
```

Verify size matches the source (~tens of MB). This unblocks J's Docker build because `docker-compose.yml` mounts `./data:/app/data:ro`.

Commit immediately so the team can pull:
```powershell
git add data/sensor_data.csv
# if the file is huge, check .gitignore — may need git-lfs or to leave it untracked
git commit -m "M: add data/ dir with sensor CSV (unblocks docker mount)"
```
**Decision point:** if the CSV is >50 MB, **don't commit it** — instead commit a `data/.gitkeep` and tell the team to copy the CSV manually from the repo root. Document this in the commit message.

### Step 1.2 — `backend/app/tools/sensor_tools.py` (55 min)

**Required public functions** (exact names — K imports these):

```python
def load_sensor_data(ipc_id: str | None = None) -> pd.DataFrame: ...
def compute_utilization_stats(ipc_id: str) -> dict: ...
def get_fleet_summary() -> dict: ...
def get_ipc_history(ipc_id: str, days: int = 30) -> list[dict]: ...
```

**Module skeleton (paste this and fill in):**

```python
"""Sensor data tools — read-only access to the CSV for the Fleet Analyst agent."""
import os
import logging
from functools import lru_cache
import pandas as pd

log = logging.getLogger(__name__)
SENSOR_DATA_PATH = os.getenv("SENSOR_DATA_PATH", "/app/data/sensor_data.csv")


@lru_cache(maxsize=1)
def _load_raw() -> pd.DataFrame:
    """Load the CSV once per process. Adds derived columns: CpuMHz_num, cpu_pct."""
    df = pd.read_csv(
        SENSOR_DATA_PATH,
        sep=";", decimal=",", dayfirst=True, parse_dates=["time"],
    )
    # CpuMHz can be "2400" or composite "2400 2400" — take first token
    df["CpuMHz_num"] = df["CpuMHz"].astype(str).str.split().str[0].astype(float)
    df["cpu_pct"] = 100.0 * df["AvgValue"] / df["CpuMHz_num"]
    # drop physically impossible readings
    df = df[df["cpu_pct"] <= 100].copy()
    return df


def load_sensor_data(ipc_id: str | None = None) -> pd.DataFrame:
    df = _load_raw()
    if ipc_id is not None:
        df = df[df["IPC"] == ipc_id].copy()
    return df


def compute_utilization_stats(ipc_id: str) -> dict:
    s = load_sensor_data(ipc_id)["cpu_pct"]
    if s.empty:
        return {"ipc_id": ipc_id, "mean": None, "p50": None, "p95": None, "max": None, "days_observed": 0}
    return {
        "ipc_id": ipc_id,
        "mean":  float(s.mean()),
        "p50":   float(s.quantile(0.50)),
        "p95":   float(s.quantile(0.95)),
        "max":   float(s.max()),
        "days_observed": int(load_sensor_data(ipc_id)["time"].dt.normalize().nunique()),
    }


def get_fleet_summary() -> dict:
    """Aggregate counts. Imports classify_ipc lazily to avoid circular import."""
    from app.tools.classifier_tools import classify_ipc  # local import on purpose
    df = _load_raw()
    ipcs = df["IPC"].unique()
    labels = {ipc: classify_ipc(ipc)["label"] for ipc in ipcs}
    count_per_label = pd.Series(labels).value_counts().to_dict()
    factory_breakdown = (
        df.drop_duplicates("IPC")
          .groupby("Data Factory")["IPC"].nunique()
          .to_dict()
    )
    return {
        "total_ipcs": int(len(ipcs)),
        "count_per_label": {k: int(v) for k, v in count_per_label.items()},
        "factory_breakdown": {k: int(v) for k, v in factory_breakdown.items()},
    }


def get_ipc_history(ipc_id: str, days: int = 30) -> list[dict]:
    df = load_sensor_data(ipc_id).sort_values("time")
    if df.empty:
        return []
    cutoff = df["time"].max() - pd.Timedelta(days=days)
    df = df[df["time"] >= cutoff]
    return [
        {"date": t.strftime("%Y-%m-%d"), "cpu_pct": float(p)}
        for t, p in zip(df["time"], df["cpu_pct"])
    ]
```

**Self-test before the T+1:00 sync:**

```python
# scratch_test.py — run from backend/ with SENSOR_DATA_PATH set to the host path
from app.tools.sensor_tools import get_fleet_summary, compute_utilization_stats, load_sensor_data
print(get_fleet_summary())               # expect total_ipcs == 4261
df = load_sensor_data()
ipc = df["IPC"].iloc[0]
print(compute_utilization_stats(ipc))    # expect 4 numeric values
```

If `total_ipcs` is not exactly **4261**, something in the load path is wrong — fix before handoff.

### Step 1.3 — Hand off to K at T+1:00

Tell K in chat:
> `sensor_tools.py` is on `m/data-tools-layer`. Public surface: `load_sensor_data`, `compute_utilization_stats`, `get_fleet_summary`, `get_ipc_history`. Note `get_fleet_summary` lazy-imports `classify_ipc` — that's fine, classifier_tools lands in hour 2.

---

## Hour 2 (T+1:00 → T+2:00)

Three files, in this order: `classifier_tools.py` → `rules.json` → `memory_tools.py`. The classifier is shortest, do it first to unblock K.

### Step 2.1 — `backend/app/tools/classifier_tools.py` (15 min)

```python
"""MVP classifier — hardcoded thresholds on cpu_p95."""
from app.tools.sensor_tools import compute_utilization_stats, load_sensor_data, _load_raw


def classify_ipc(ipc_id: str) -> dict:
    stats = compute_utilization_stats(ipc_id)
    p95 = stats["p95"]
    if p95 is None:
        return {"ipc_id": ipc_id, "label": "unknown", "rule_fired": "no_data", "cpu_p95": None}
    if p95 < 30:
        label, rule = "underutilized", "r1"
    elif p95 < 65:
        label, rule = "healthy", "r2"
    elif p95 < 85:
        label, rule = "at_risk", "r3"
    else:
        label, rule = "overloaded", "r4"
    return {"ipc_id": ipc_id, "label": label, "rule_fired": rule, "cpu_p95": p95}


def flag_anomalies(ipc_id: str | None = None) -> list[dict]:
    """Flag IPCs with cpu_p95 > 85 OR days_observed < 10."""
    df = _load_raw()
    targets = [ipc_id] if ipc_id else df["IPC"].unique().tolist()
    flagged = []
    for ipc in targets:
        s = compute_utilization_stats(ipc)
        if s["p95"] is not None and (s["p95"] > 85 or s["days_observed"] < 10):
            reason = "high_p95" if s["p95"] > 85 else "low_coverage"
            flagged.append({"ipc_id": ipc, "reason": reason, **s})
    return flagged
```

**Note:** `flag_anomalies` over the full fleet is O(4261 × stats-compute). Acceptable for the demo, but if it feels slow, vectorize with a single `groupby("IPC")["cpu_pct"].quantile(0.95)`.

### Step 2.2 — `backend/app/classifier/rules.json` (5 min)

```json
[
  {"id": "r1", "label": "underutilized", "conditions": [{"feature": "cpu_p95", "operator": "<",  "value": 30}]},
  {"id": "r2", "label": "healthy",       "conditions": [{"feature": "cpu_p95", "operator": ">=", "value": 30}, {"feature": "cpu_p95", "operator": "<",  "value": 65}]},
  {"id": "r3", "label": "at_risk",       "conditions": [{"feature": "cpu_p95", "operator": ">=", "value": 65}, {"feature": "cpu_p95", "operator": "<",  "value": 85}]},
  {"id": "r4", "label": "overloaded",    "conditions": [{"feature": "cpu_p95", "operator": ">=", "value": 85}]}
]
```

The `classifier_tools.py` MVP doesn't actually read this file — it's there for the rubric. If you have time at the end of hour 3, refactor `classify_ipc` to load and apply `rules.json` at import time. Optional.

### Step 2.3 — `backend/app/tools/memory_tools.py` (40 min)

```python
"""SQLite-backed long-term memory for HITL decisions and operator preferences."""
import os
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime

log = logging.getLogger(__name__)
DATABASE_PATH = os.getenv("DATABASE_PATH", "/app/data/memory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ipc_id        TEXT    NOT NULL,
    action        TEXT    NOT NULL,
    rationale     TEXT,
    status        TEXT    NOT NULL,             -- 'approved' | 'rejected' | 'pending'
    operator_note TEXT,
    created_at    TEXT    NOT NULL              -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS preferences (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@contextmanager
def _conn():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)


def save_decision(ipc_id: str, action: str, rationale: str, status: str,
                  operator_note: str | None = None) -> int:
    init_db()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO decisions (ipc_id, action, rationale, status, operator_note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (ipc_id, action, rationale, status, operator_note, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def load_past_decisions(ipc_id: str | None = None) -> list[dict]:
    init_db()
    with _conn() as c:
        if ipc_id:
            rows = c.execute(
                "SELECT * FROM decisions WHERE ipc_id = ? ORDER BY created_at DESC", (ipc_id,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM decisions ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def get_session_context(limit: int = 10) -> str:
    """Plain-text summary of recent decisions for injection into the Orchestrator system prompt."""
    decisions = load_past_decisions()[:limit]
    if not decisions:
        return "No prior decisions on record."
    lines = ["Recent operator decisions:"]
    for d in decisions:
        note = f" — note: {d['operator_note']}" if d.get("operator_note") else ""
        lines.append(
            f"- [{d['created_at'][:10]}] IPC={d['ipc_id']} action={d['action']} status={d['status']}{note}"
        )
    return "\n".join(lines)
```

**Self-test:**

```python
from app.tools.memory_tools import save_decision, load_past_decisions, get_session_context
save_decision("IPC-TEST", "decommission", "p95 < 5%", "approved", "trial run")
print(load_past_decisions("IPC-TEST"))
print(get_session_context())
```

### Step 2.4 — Hand off to K at T+2:00

> `memory_tools.py` ready. Surface: `save_decision(ipc_id, action, rationale, status, operator_note=None)`, `load_past_decisions(ipc_id=None)`, `get_session_context()`. SQLite auto-init on first call. DB at `$DATABASE_PATH`.

---

## Hour 3 (T+2:00 → T+3:00)

### Step 3.1 — End-to-end isolation test (20 min)

Create `backend/scratch_e2e.py` (delete before submit):

```python
import os
os.environ["SENSOR_DATA_PATH"] = r"C:\Users\tmiha\Documents\Touchpulse\Assignment\the-smart-factory\data\sensor_data.csv"
os.environ["DATABASE_PATH"]   = r"C:\Users\tmiha\Documents\Touchpulse\Assignment\the-smart-factory\data\memory.db"

from app.tools.sensor_tools import load_sensor_data, get_fleet_summary, compute_utilization_stats
from app.tools.classifier_tools import classify_ipc, flag_anomalies
from app.tools.memory_tools import save_decision, load_past_decisions, get_session_context

summary = get_fleet_summary()
assert summary["total_ipcs"] == 4261, f"expected 4261, got {summary['total_ipcs']}"
print("FLEET:", summary)

df = load_sensor_data()
sample_ipcs = df["IPC"].drop_duplicates().head(3).tolist()
for ipc in sample_ipcs:
    print("STATS:",     compute_utilization_stats(ipc))
    print("CLASSIFY:",  classify_ipc(ipc))

save_decision(sample_ipcs[0], "decommission", "p95 < 30 sustained", "approved")
print("PAST:", load_past_decisions(sample_ipcs[0]))
print("CTX:\n" + get_session_context())
```

Pass criteria:
- `total_ipcs == 4261`
- All 4 labels (`underutilized`, `healthy`, `at_risk`, `overloaded`) appear somewhere across the fleet — if one is empty the thresholds may not match this dataset; report to K but don't change them.
- Decision round-trips through SQLite.

### Step 3.2 — Sanity-check fleet split (5 min)

Print `summary["count_per_label"]`. Eyeball it: with the 30/65/85 thresholds you should see *most* IPCs as `underutilized` or `healthy`, a smaller `at_risk`, and a small `overloaded` tail. If 100% land in one bucket, something is wrong with `cpu_pct` (most likely the `CpuMHz` parsing).

### Step 3.3 — Run `simplify` on each file (10 min)

Use the `/simplify` slash command on `sensor_tools.py`, `classifier_tools.py`, `memory_tools.py`. Accept changes that remove dead code or duplication; reject anything that changes the public function signatures K depends on.

### Step 3.4 — Help K debug tool wiring (remainder)

Common failure modes K will hit:

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError: /app/data/sensor_data.csv` | env not set, or running on host | `export SENSOR_DATA_PATH=...` or check Docker mount |
| `KeyError: 'IPC'` | Loaded with default sep | Confirm `_load_raw` ran, not a re-implementation |
| Tool result is `"<DataFrame>"` | LangChain stringified a df | Tools must return dicts/lists, not DataFrames — fix the offender |
| `np.int64 is not JSON serializable` | Forgot to cast | Wrap return values in `int()`/`float()` |
| Slow first agent turn | CSV reload | Confirm `@lru_cache` is on `_load_raw` |

### Step 3.5 — Final commit + push

```powershell
git add backend/app/tools/ backend/app/classifier/rules.json
git commit -m "M: tools layer (sensor, classifier, memory) + classifier rules"
git push -u origin m/data-tools-layer
```

Don't merge to master yourself — let the team integrate at T+3:00.

---

## Definition of done

- [ ] `data/sensor_data.csv` exists (or `data/.gitkeep` + manual-copy note in commit msg).
- [ ] `sensor_tools.py` has 4 public functions, all return JSON-safe types, CSV cached.
- [ ] `classifier_tools.py` has `classify_ipc` and `flag_anomalies`.
- [ ] `rules.json` matches the four MVP thresholds.
- [ ] `memory_tools.py` has `save_decision`, `load_past_decisions`, `get_session_context`, and `init_db` is idempotent.
- [ ] E2E scratch test passes: `total_ipcs == 4261`, all labels populated, decision round-trips.
- [ ] No `print()` left in production modules; no scratch files committed.
- [ ] Branch pushed; K notified at each handoff (T+1:00, T+2:00).

---

## Cut-list if the clock runs out

| Drop | Cost |
|---|---|
| `flag_anomalies` | None — Orchestrator MVP doesn't call it |
| `get_ipc_history` | Loses the dashboard endpoint, chat unaffected |
| `preferences` table | Good-tier only; remove from schema if not used |
| Loading `rules.json` in `classify_ipc` | Already optional — hardcoded thresholds satisfy MVP |
| `simplify` pass | Skip if K is blocked on you |

**Never cut:** `get_fleet_summary`, `classify_ipc`, `save_decision`, `load_past_decisions`, `get_session_context`. K and J both depend on these — cutting any one breaks the demo.

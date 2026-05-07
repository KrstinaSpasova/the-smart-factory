# M's Layer — Data + Tools Architecture

## 1. Scope & Position in the System

M's layer is the **read-only data plane** plus the **persistence plane** for HITL decisions. It sits below the agent layer (K) and the API layer (J), exposing a stable Python function surface that LangChain tools wrap.

```mermaid
flowchart TB
    subgraph J["J — API Layer"]
        FA["FastAPI /chat, /fleet/summary, /decisions"]
        ST["Streamlit UI"]
    end

    subgraph K["K — Agent Layer"]
        OR["Orchestrator<br/>(HITL gate)"]
        FL["Fleet Analyst<br/>(read-only)"]
        MM["Memory Manager"]
    end

    subgraph M["M — Data + Tools Layer"]
        direction TB
        SR["sensor_tools.py"]
        CL["classifier_tools.py"]
        ME["memory_tools.py"]
        RJ[("rules.json<br/>(reference, MVP-unused)")]
    end

    subgraph DATA["Storage"]
        CSV[("sensor_data.csv<br/>16 MB · 220k rows")]
        DB[("memory.db<br/>SQLite")]
    end

    ST --> FA
    FA --> OR
    OR --> FL
    OR --> MM
    FL --> SR
    FL --> CL
    MM --> ME
    CL -.imports.-> SR
    SR --> CSV
    ME --> DB

    style M fill:#0d2845,stroke:#2979c0,stroke-width:2px,color:#fff
    style DATA fill:#2b1d00,stroke:#c49000,color:#fff
```

**The contract:** every M function returns JSON-serializable types (dict/list/primitive). No DataFrames, no `np.int64`. This is what lets LangChain's tool serializer not mangle results in the agent trace.

---

## 2. Module Dependency Graph

```mermaid
flowchart LR
    SR["sensor_tools.py"]
    CL["classifier_tools.py"]
    ME["memory_tools.py"]
    RJ[("rules.json")]
    PD[["pandas"]]
    SQ[["sqlite3"]]

    SR --> PD
    CL --> SR
    SR -. lazy import<br/>at call time .-> CL
    ME --> SQ

    style SR fill:#0d2b0d,stroke:#4a9a4a,color:#fff
    style CL fill:#2b0d0d,stroke:#9a4a4a,color:#fff
    style ME fill:#0d0d2b,stroke:#4a4a9a,color:#fff
```

**Why the lazy import?** `classifier_tools` imports `compute_utilization_stats` from `sensor_tools`. But `sensor_tools.get_fleet_summary` needs to classify every IPC, so it calls `classify_ipc`. That's a circular import at module-load time — the lazy `from app.tools.classifier_tools import classify_ipc` inside `get_fleet_summary` breaks the cycle by deferring it to call time. `memory_tools` is fully independent — no cross-imports with the other two.

---

## 3. `sensor_tools.py` — Data Loading & Stats

### 3.1 Load Pipeline

```mermaid
flowchart TB
    A["CSV on disk<br/>European format"] --> B["_load_all<br/>@lru_cache"]
    B --> B1["pd.read_csv<br/>sep=';' decimal=','<br/>dayfirst=True<br/>parse_dates=['time']"]
    B1 --> B2["Derive CpuMHz_num<br/>str.split first token<br/>handles '2400 2400'"]
    B2 --> B3["Derive cpu_pct =<br/>100 x AvgValue / CpuMHz_num"]
    B3 --> C[("Cached full DataFrame<br/>~220k rows, 4261 IPCs")]

    C --> D["_load_raw<br/>@lru_cache"]
    D --> D1["Filter cpu_pct <= 100<br/>drops outlier rows"]
    D1 --> E[("Cached filtered DataFrame<br/>~220k rows, 4251 IPCs")]

    style C fill:#2b1d00,stroke:#c49000,color:#fff
    style E fill:#2b1d00,stroke:#c49000,color:#fff
```

**Two-level cache.** Both `_load_all` and `_load_raw` are `@lru_cache(maxsize=1)`, so the CSV is parsed exactly once per process. The split is necessary because:

- **Stats functions** (`compute_utilization_stats`, `get_ipc_history`) want filtered data — outlier rows would corrupt p95.
- **`get_fleet_summary`** wants the *unfiltered* IPC list — otherwise the 10 outlier-only IPCs (e.g. `ITLT1593` with rated 9,600 MHz but reported 300,000 MHz) vanish from the count, and `total_ipcs` becomes 4251 instead of the spec'd 4261.

### 3.2 Public Surface

| Function | Signature | Returns |
|---|---|---|
| `load_sensor_data` | `(ipc_id: str \| None = None)` | filtered DataFrame, optionally narrowed to one IPC |
| `compute_utilization_stats` | `(ipc_id: str)` | `{ipc_id, mean, p50, p95, max, days_observed}` |
| `get_fleet_summary` | `()` | `{total_ipcs, count_per_label, factory_breakdown}` |
| `get_ipc_history` | `(ipc_id, days=30)` | `[{date, cpu_pct}, ...]` |

### 3.3 The CPU% Calculation

```mermaid
flowchart LR
    A["AvgValue<br/>(measured MHz)"] --> C
    B["CpuMHz<br/>(rated, may be<br/>'2400 2400')"] --> B1["Take first token<br/>cast to float"]
    B1 --> C["cpu_pct =<br/>100 x Avg / Rated"]
    C --> D{"cpu_pct > 100?"}
    D -->|yes| E["Drop row<br/>physically impossible"]
    D -->|no| F["Keep for stats"]
```

This is the non-obvious derivation the architecture spec mandates. The CSV ships raw MHz; utilization % is a derived feature added at load time.

---

## 4. `classifier_tools.py` — Threshold Classification

### 4.1 Decision Tree

```mermaid
flowchart TB
    A["classify_ipc(ipc_id)"] --> B["compute_utilization_stats"]
    B --> C{"p95 is None?"}
    C -->|yes| Z["{label: unknown,<br/>rule_fired: no_data}"]
    C -->|no| D{"p95 < 30?"}
    D -->|yes| L1["underutilized (r1)"]
    D -->|no| E{"p95 < 65?"}
    E -->|yes| L2["healthy (r2)"]
    E -->|no| F{"p95 < 85?"}
    F -->|yes| L3["at_risk (r3)"]
    F -->|no| L4["overloaded (r4)"]

    style L1 fill:#0d2b0d,stroke:#4a9a4a,color:#fff
    style L2 fill:#0d1f2b,stroke:#4a7a9a,color:#fff
    style L3 fill:#2b2000,stroke:#9a8000,color:#fff
    style L4 fill:#2b0d0d,stroke:#9a4a4a,color:#fff
    style Z fill:#1a1a1a,stroke:#555,color:#aaa
```

### 4.2 Observed Fleet Distribution

| Label | Threshold | Count | % |
|---|---|---|---|
| `underutilized` | `p95 < 30` | 3,923 | 92.1% |
| `healthy` | `30 <= p95 < 65` | 264 | 6.2% |
| `at_risk` | `65 <= p95 < 85` | 44 | 1.0% |
| `overloaded` | `p95 >= 85` | 20 | 0.5% |
| `unknown` | no usable rows | 10 | 0.2% |
| **Total** | | **4,261** | |

### 4.3 `rules.json` — Spec Reference, MVP-Unused

```mermaid
flowchart LR
    A["rules.json"] -.->|"Good tier:<br/>load at import,<br/>walk rules"| B["classify_ipc<br/>data-driven"]
    A -->|"MVP:<br/>satisfies rubric"| C["sits on disk"]
    D["Hardcoded if/elif"] ==>|"MVP path"| B
```

### 4.4 `flag_anomalies` — Audit Tool

```mermaid
flowchart LR
    A["All IPCs<br/>(or one)"] --> B["For each IPC"]
    B --> C["compute_utilization_stats"]
    C --> D{"p95 > 85<br/>OR<br/>days_observed < 10?"}
    D -->|yes| E["Append with reason:<br/>high_p95 or low_coverage"]
    D -->|no| F["Skip"]
    E --> G["list of flagged dicts"]
```

---

## 5. `memory_tools.py` — HITL Persistence

### 5.1 SQLite Schema

```mermaid
erDiagram
    DECISIONS {
        INTEGER id PK
        TEXT ipc_id
        TEXT action
        TEXT rationale
        TEXT status
        TEXT operator_note
        TEXT created_at
    }
    PREFERENCES {
        TEXT key PK
        TEXT value
        TEXT updated_at
    }
```

Two flat tables, no foreign keys. `decisions` is append-only — operator history is immutable. `preferences` is reserved for the Good tier (e.g. "always reject decommission for Factory 5").

### 5.2 Lifecycle of a Decision

```mermaid
sequenceDiagram
    participant Op as Operator
    participant Or as Orchestrator
    participant Mt as memory_tools
    participant Db as memory.db

    Op->>Or: "Decommission ITLT4301"
    Or->>Or: classify_ipc, get stats
    Or->>Mt: load_past_decisions("ITLT4301")
    Mt->>Db: SELECT WHERE ipc_id=?
    Db-->>Mt: rows
    Mt-->>Or: past decisions
    Or-->>Op: "Recommend decommission. Approve?"
    Op->>Or: "Approve"
    Or->>Mt: save_decision(...)
    Mt->>Db: init_db (idempotent)
    Mt->>Db: INSERT INTO decisions
    Db-->>Mt: lastrowid
    Mt-->>Or: id=42
    Or-->>Op: "Saved (decision 42)"
```

**Two important design points:**

1. **`init_db` is idempotent and called by every write.** No bootstrap step. The first `save_decision` on a fresh deploy creates the schema via `CREATE TABLE IF NOT EXISTS`.
2. **The connection is per-call, not pooled.** `_conn()` opens/commits/closes per operation. Fine for SQLite at this scale and avoids threading concerns with FastAPI.

### 5.3 `get_session_context` — Memory Bridging

```mermaid
flowchart LR
    A["Orchestrator<br/>session start"] --> B["get_session_context()"]
    B --> C["load_past_decisions()"]
    C --> D["Take last 10"]
    D --> E["Format as<br/>plain-text bullets"]
    E --> F["Inject into<br/>system prompt<br/>via memory_context"]
```

---

## 6. End-to-End Data Flow (Demo Path)

```mermaid
sequenceDiagram
    autonumber
    participant U as Operator
    participant API as FastAPI
    participant O as Orchestrator
    participant FA as Fleet Analyst
    participant ST as sensor_tools
    participant CT as classifier_tools
    participant MT as memory_tools
    participant CSV as sensor_data.csv
    participant SQL as memory.db

    U->>API: "Which IPCs are at risk?"
    API->>O: invoke
    O->>MT: get_session_context()
    MT->>SQL: SELECT recent decisions
    SQL-->>MT: rows
    MT-->>O: plain-text summary

    O->>FA: delegate analysis
    FA->>ST: get_fleet_summary()
    ST->>CSV: load if not cached
    CSV-->>ST: 220k rows
    ST->>CT: classify_ipc per IPC
    CT->>ST: compute_utilization_stats
    ST-->>CT: stats dict
    CT-->>ST: label + rule
    ST-->>FA: summary dict
    FA-->>O: structured facts

    O-->>API: "Found 44 at_risk. Approve?"
    API-->>U: response

    U->>API: "Approve ITLT4301"
    API->>O: invoke
    O->>MT: save_decision(ITLT4301,...)
    MT->>SQL: INSERT
    SQL-->>MT: id=43
    MT-->>O: 43
    O-->>API: "Recorded as decision 43"
    API-->>U: response
```

---

## 7. Failure Modes & Defenses

| Failure | Defense in M's layer |
|---|---|
| CSV missing | Plain `FileNotFoundError` with the path in the message |
| CSV not European-formatted | Explicit `sep=";"`, `decimal=","` — never silently misparsed |
| IPC has no rows / all-outlier rows | `compute_utilization_stats` returns `{p95: None, days_observed: 0}` |
| Unknown IPC passed to classifier | Returns `{label: "unknown", rule_fired: "no_data"}` |
| `memory.db` directory missing | `os.makedirs(..., exist_ok=True)` in `_conn()` |
| `np.int64` in tool return values | All scalars cast to `int()`/`float()` before return |

---

## 8. Cache Map

```mermaid
flowchart LR
    subgraph cache["Process-lifetime lru_cache"]
        A["_load_all"]
        B["_load_raw"]
    end

    subgraph computed["Re-computed each call"]
        C["compute_utilization_stats"]
        D["classify_ipc"]
        E["get_fleet_summary"]
        F["get_ipc_history"]
    end

    subgraph db["Per-call SQLite connection"]
        G["save_decision"]
        H["load_past_decisions"]
        I["get_session_context"]
    end

    A -.-> B
    B -.-> C
    C -.-> D
    A -.-> E
    D -.-> E
```

`get_fleet_summary` is the slow path — 4,261 sequential `compute_utilization_stats` calls (~5s cold). Acceptable for MVP demo; vectorizable with a single `groupby("IPC")["cpu_pct"].quantile(0.95)` if needed.

---

## 9. Definition of Done

| Spec item | State |
|---|---|
| `data/sensor_data.csv` mountable (gitignored, copy manually) | done |
| `sensor_tools.py` — 4 public fns, JSON-safe, cached | done |
| `classifier_tools.py` — `classify_ipc` + `flag_anomalies` | done |
| `rules.json` — four MVP thresholds | done |
| `memory_tools.py` — save/load/context + idempotent init | done |
| `total_ipcs == 4261` E2E verified | done |
| All 4 labels populated | done |
| Decision SQLite round-trip verified | done |
| No `print()` in production modules | done |
| Branch merged to master | done (commit d89a750) |

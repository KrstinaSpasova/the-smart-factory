"""MVP classifier — hardcoded thresholds on cpu_p95."""
from app.tools.sensor_tools import compute_utilization_stats, _load_raw


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
    return {"ipc_id": ipc_id, "label": label, "rule_fired": rule, "cpu_p95": float(p95)}


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

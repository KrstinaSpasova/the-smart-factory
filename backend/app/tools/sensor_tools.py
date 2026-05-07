"""Sensor data tools — read-only access to the CSV for the Fleet Analyst agent."""
import os
import logging
from functools import lru_cache
import pandas as pd

log = logging.getLogger(__name__)
SENSOR_DATA_PATH = os.getenv("SENSOR_DATA_PATH", "/app/data/sensor_data.csv")


@lru_cache(maxsize=1)
def _load_all() -> pd.DataFrame:
    """Load the CSV once per process with all derived columns, before outlier filtering."""
    df = pd.read_csv(
        SENSOR_DATA_PATH,
        sep=";", decimal=",", dayfirst=True, parse_dates=["time"],
    )
    df["CpuMHz_num"] = df["CpuMHz"].astype(str).str.split().str[0].astype(float)
    df["cpu_pct"] = 100.0 * df["AvgValue"] / df["CpuMHz_num"]
    return df


@lru_cache(maxsize=1)
def _load_raw() -> pd.DataFrame:
    """Filtered view — cpu_pct <= 100 (drops physically impossible readings)."""
    return _load_all()[_load_all()["cpu_pct"] <= 100].copy()


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
    # Use unfiltered data for IPC list so outlier-only IPCs are still counted
    all_df = _load_all()
    ipcs = all_df["IPC"].unique()
    labels = {ipc: classify_ipc(ipc)["label"] for ipc in ipcs}
    count_per_label = pd.Series(labels).value_counts().to_dict()
    factory_breakdown = (
        all_df.drop_duplicates("IPC")
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

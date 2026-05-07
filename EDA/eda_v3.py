"""EDA v3 — deeper checks: integrity, outliers, time coverage, multi-CPU anomalies."""
import pandas as pd
import numpy as np

CSV = r"C:\Users\tmiha\Documents\Touchpulse\Assignment\Database - Testcase_agentic_ai_V1.0.zip.csv"
df = pd.read_csv(CSV, sep=";", decimal=",", dayfirst=True, parse_dates=["time"])

print("=" * 70)
print("INTEGRITY CHECKS")
print("=" * 70)
print("Rows where Min > Avg :", (df["MinValue"] > df["AvgValue"]).sum())
print("Rows where Avg > Max :", (df["AvgValue"] > df["MaxValue"]).sum())
print("Rows where Min > Max :", (df["MinValue"] > df["MaxValue"]).sum())
print("Rows with Min == 0   :", (df["MinValue"] == 0).sum())
print("Rows with Avg == 0   :", (df["AvgValue"] == 0).sum())

print("=" * 70)
print("CpuMHz: composite (multi-CPU) entries — contain a space")
print("=" * 70)
mask_multi = df["CpuMHz"].astype(str).str.contains(" ")
print("Rows with composite CpuMHz:", mask_multi.sum())
print("Distinct composite values:")
print(df.loc[mask_multi, "CpuMHz"].value_counts().to_string())

print("=" * 70)
print("TIME COVERAGE per IPC")
print("=" * 70)
records_per_ipc = df.groupby("IPC").size()
print(records_per_ipc.describe().to_string())
print("\nIPCs with >61 records (more than 1 row per day → multiple CPUs):",
      (records_per_ipc > 61).sum())
print("IPCs with exactly 61 (full coverage):", (records_per_ipc == 61).sum())
print("IPCs with <61 (gaps):", (records_per_ipc < 61).sum())

# Are duplicates same (IPC, time) — i.e. machine reported multiple times same day?
dup_keys = df.duplicated(subset=["IPC", "time"], keep=False)
print(f"\nRows sharing (IPC,time) with another row: {dup_keys.sum()}")
print("Sample of (IPC,time) duplicates:")
print(df[dup_keys].sort_values(["IPC","time"]).head(10).to_string())

print("=" * 70)
print("ONE IPC → ONE Data Factory? ONE CpuMHz?")
print("=" * 70)
ipc_factories = df.groupby("IPC")["Data Factory"].nunique()
ipc_cpus = df.groupby("IPC")["CpuMHz"].nunique()
print("IPCs mapped to >1 Data Factory:", (ipc_factories > 1).sum())
print("IPCs mapped to >1 CpuMHz value :", (ipc_cpus > 1).sum())
if (ipc_cpus > 1).sum():
    print("  example IPCs with multiple CpuMHz:")
    multi_cpu_ipcs = ipc_cpus[ipc_cpus > 1].head(5).index
    for ipc in multi_cpu_ipcs:
        vals = df.loc[df["IPC"] == ipc, "CpuMHz"].unique()
        print(f"    {ipc}: {vals}")

print("=" * 70)
print("OUTLIERS in AvgValue")
print("=" * 70)
q99 = df["AvgValue"].quantile(0.99)
q999 = df["AvgValue"].quantile(0.999)
print(f"99th pct: {q99:.2f}")
print(f"99.9th pct: {q999:.2f}")
print(f"Rows above 99.9th pct: {(df['AvgValue']>q999).sum()}")
print("Top 10 AvgValue rows:")
print(df.nlargest(10, "AvgValue").to_string())

print("=" * 70)
print("LOAD RATIO (AvgValue / CpuMHz_numeric) — % CPU used")
print("=" * 70)
# Use first numeric token from CpuMHz
df["CpuMHz_num"] = df["CpuMHz"].astype(str).str.split().str[0].astype(float)
df["LoadPct"] = 100 * df["AvgValue"] / df["CpuMHz_num"]
print(df["LoadPct"].describe().to_string())
print("Rows with LoadPct > 100% (avg exceeds rated CPU):",
      (df["LoadPct"] > 100).sum())
print("Rows with LoadPct > 100% (using first CpuMHz token only).")

print("=" * 70)
print("PER DATA FACTORY summary of AvgValue")
print("=" * 70)
print(df.groupby("Data Factory")["AvgValue"].describe().to_string())

print("=" * 70)
print("DAILY TOTAL AvgValue (factory-level trend)")
print("=" * 70)
daily = df.groupby(["time", "Data Factory"])["AvgValue"].mean().unstack()
print(daily.head(10).to_string())
print("...")
print(daily.tail(5).to_string())

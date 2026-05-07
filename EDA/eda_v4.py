"""EDA v4 — same as v3 but ASCII-only output for Windows cp1252 console."""
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
print("CpuMHz: composite (multi-CPU) entries (contain a space)")
print("=" * 70)
mask_multi = df["CpuMHz"].astype(str).str.contains(" ")
print("Rows with composite CpuMHz:", mask_multi.sum())
print(df.loc[mask_multi, "CpuMHz"].value_counts().to_string())

print("=" * 70)
print("TIME COVERAGE per IPC (full window = 61 days)")
print("=" * 70)
records_per_ipc = df.groupby("IPC").size()
print(records_per_ipc.describe().to_string())
print()
print("IPCs with > 61 records (multiple rows per day):", (records_per_ipc > 61).sum())
print("IPCs with = 61 records (full coverage)       :", (records_per_ipc == 61).sum())
print("IPCs with < 61 records (gaps)                :", (records_per_ipc < 61).sum())
print("IPCs with only 1 record                      :", (records_per_ipc == 1).sum())

dup_keys = df.duplicated(subset=["IPC", "time"], keep=False)
print()
print("Rows sharing (IPC,time) with another row:", dup_keys.sum())
print("Sample of (IPC,time) duplicates:")
print(df[dup_keys].sort_values(["IPC","time"]).head(10).to_string())

print("=" * 70)
print("ONE IPC -> ONE Data Factory? ONE CpuMHz?")
print("=" * 70)
ipc_factories = df.groupby("IPC")["Data Factory"].nunique()
ipc_cpus = df.groupby("IPC")["CpuMHz"].nunique()
print("IPCs mapped to >1 Data Factory:", (ipc_factories > 1).sum())
print("IPCs mapped to >1 CpuMHz value:", (ipc_cpus > 1).sum())
if (ipc_cpus > 1).sum():
    print("  example IPCs with multiple CpuMHz values:")
    for ipc in ipc_cpus[ipc_cpus > 1].head(5).index:
        vals = df.loc[df["IPC"] == ipc, "CpuMHz"].unique()
        print(f"    {ipc}: {list(vals)}")

print("=" * 70)
print("OUTLIERS in AvgValue")
print("=" * 70)
q99  = df["AvgValue"].quantile(0.99)
q999 = df["AvgValue"].quantile(0.999)
print(f"99.0th pct : {q99:.2f}")
print(f"99.9th pct : {q999:.2f}")
print(f"Rows above 99.9th pct: {(df['AvgValue']>q999).sum()}")
print("Top 10 AvgValue rows:")
print(df.nlargest(10, "AvgValue").to_string())

print("=" * 70)
print("LOAD RATIO = 100 * AvgValue / first(CpuMHz)")
print("=" * 70)
df["CpuMHz_num"] = df["CpuMHz"].astype(str).str.split().str[0].astype(float)
df["LoadPct"]    = 100 * df["AvgValue"] / df["CpuMHz_num"]
print(df["LoadPct"].describe().to_string())
print("Rows with LoadPct > 100%:", (df["LoadPct"] > 100).sum())
print("Rows with LoadPct > 50% :", (df["LoadPct"] > 50).sum())

print("=" * 70)
print("PER DATA FACTORY: AvgValue summary")
print("=" * 70)
print(df.groupby("Data Factory")["AvgValue"].describe().to_string())
print()
print("Distinct IPCs per factory:")
print(df.groupby("Data Factory")["IPC"].nunique().to_string())

print("=" * 70)
print("DAILY MEAN AvgValue per Data Factory (head/tail)")
print("=" * 70)
daily = df.groupby(["time", "Data Factory"])["AvgValue"].mean().unstack()
print(daily.head(7).to_string())
print("...")
print(daily.tail(7).to_string())

print("=" * 70)
print("WEEKDAY pattern (mean AvgValue by day-of-week)")
print("=" * 70)
df["dow"] = df["time"].dt.day_name()
print(df.groupby("dow")["AvgValue"].agg(["mean","median","count"]).to_string())

print("=" * 70)
print("DATES PRESENT (count of unique dates):", df["time"].nunique())
all_dates = pd.date_range(df["time"].min(), df["time"].max(), freq="D")
missing = sorted(set(all_dates) - set(df["time"].unique()))
print("Calendar dates with NO data at all:", len(missing))
for d in missing:
    print("  ", d.date())

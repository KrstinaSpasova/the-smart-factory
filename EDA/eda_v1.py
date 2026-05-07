"""EDA v1 — initial inspection: shape, dtypes, head, missing, basic describe."""
import pandas as pd

CSV = r"C:\Users\tmiha\Documents\Touchpulse\Assignment\Database - Testcase_agentic_ai_V1.0.zip.csv"

df = pd.read_csv(CSV)

print("=" * 70)
print("SHAPE:", df.shape)
print("=" * 70)
print("COLUMNS:")
for c in df.columns:
    print(f"  - {c}")
print("=" * 70)
print("DTYPES:")
print(df.dtypes)
print("=" * 70)
print("HEAD (5):")
print(df.head().to_string())
print("=" * 70)
print("MISSING per column:")
print(df.isna().sum())
print("=" * 70)
print("DESCRIBE (numeric):")
print(df.describe(include="number").to_string())
print("=" * 70)
print("DESCRIBE (object):")
print(df.describe(include="object").to_string())

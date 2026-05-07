# EDA Explanation - Smart Factory CPU Usage Dataset

Companion document to `eda_v1.py` ... `eda_v5.ipynb`. Explains **what** was done, **why**, and **how to read** every output.

---

## 1. The dataset at a glance

| Property | Value |
|---|---|
| File | `Database - Testcase_agentic_ai_V1.0.zip.csv` |
| Format | Semicolon-delimited (`;`), comma-decimal (`,`) - European CSV |
| Rows | 220,294 |
| Columns | 8 |
| Time window | 2021-05-01 -> 2021-06-30 (61 daily timestamps, no calendar gaps) |
| Missing values | 0 |
| Fully duplicated rows | 0 |

### Column dictionary

| Column | Type | Meaning | Notes |
|---|---|---|---|
| `IPC` | string | Industrial PC / machine identifier | 4,261 unique values, prefix `ITLT` |
| `Data Factory` | int (1-5) | Factory the IPC reports from | 5 distinct factories |
| `time` | date | Day of the measurement | Daily granularity |
| `AvgValue` | float | Mean CPU usage in MHz over the day | Heavily right-skewed |
| `MinValue` | float | Daily minimum CPU usage in MHz | `Min <= Avg <= Max` always holds |
| `MaxValue` | float | Daily maximum CPU usage in MHz | |
| `MetricId` | string | Always `CpuUsageMHz` | **Constant -> drop for modelling** |
| `CpuMHz` | string | Rated CPU frequency of the machine | Sometimes composite (e.g. `"11200 9180"`) for multi-CPU boxes |

---

## 2. Why the analysis was structured this way

EDA was iterated as a chain of versioned scripts so every step is reproducible and any one of them can be re-run in isolation.

| Version | Purpose | Result |
|---|---|---|
| `eda_v1.py` | Naive `read_csv` to discover the format | Crashed - revealed the file is `;`/`,` formatted, not `,`/`.` |
| `eda_v2.py` | Proper parsing + schema, dtypes, missingness, value counts | Established the basic shape of the data |
| `eda_v3.py` | Integrity checks, outliers, time coverage, multi-CPU rows | Failed at the end on Windows cp1252 console (Unicode arrow) |
| `eda_v4.py` | ASCII-clean rerun of v3 | Final tabular EDA used for the written summary |
| `eda_v5.ipynb` | Visual notebook (histograms, correlations, time series) | Charts to support / verify the v4 findings |

This document (`eda_explanation_v1.md`) is the human-readable companion.

---

## 3. What each script section does

### 3.1 Parsing rules (every script, top of file)

```python
pd.read_csv(CSV, sep=';', decimal=',', dayfirst=True, parse_dates=['time'])
```
- `sep=';'` and `decimal=','` are mandatory - the v1 attempt without these collapsed all 8 columns into one string column.
- `dayfirst=True` because dates are formatted `dd/mm/yyyy` (e.g. `01/05/2021` is May 1st, not January 5th).

### 3.2 Integrity checks (`eda_v3/v4`)

We assert the obvious physical invariants:
- `Min <= Avg <= Max` -> 0 violations. Good - the underlying aggregator is consistent.
- Counts of `Min == 0` (8 rows, plausible idle moments) and `Avg == 0` (0 rows).

If any of these had failed, downstream stats would be untrustworthy.

### 3.3 Time coverage (`eda_v3/v4`)

Per-IPC record counts answer: *does each machine report every day?*
- Median 54 records / 61 possible days -> most machines have small gaps.
- 3 IPCs have **more than 61** records (multiple reports per day).
- 37 IPCs appear only once - candidates for exclusion or special handling in any time-series model.

`(IPC, time)` duplicates (270 rows) are mostly explained by 3 IPCs that report under **two** different `Data Factory` values - same string ID, almost certainly two distinct physical machines.

### 3.4 IPC consistency

- 447 IPCs report **multiple distinct `CpuMHz` values** during the window. Two patterns:
  - Tiny drift like `5186 / 5188` or `9600 / 10800` -> probably real frequency scaling (DVFS).
  - Big jumps like `9576 -> 47880` -> hardware change, mis-reading, or unit issue. Worth flagging before training.

### 3.5 Outliers (`eda_v3/v4`, notebook section 9)

- 99th percentile of `AvgValue` ~ 6,874 MHz; 99.9th ~ 98,033 MHz.
- The top 10 highest values **all belong to a single IPC: `ITLT1593`** (factory 5, rated 9,600 MHz) with daily averages of 280k-350k MHz - **30x the rated frequency**, which is physically impossible. This is almost certainly a data-quality bug (unit mismatch, multi-core sum mistakenly written into a single-machine row, or counter overflow). It dominates factory 5's mean (2,566) and std (17,026).
- Recommended action: investigate or exclude `ITLT1593` (and similar suspects) before any modelling.

### 3.6 Load percentage

We added a derived `LoadPct = 100 * AvgValue / CpuMHz_num` (using the first token of any composite `CpuMHz` string).
- Median load 2.9% (idle-ish factory).
- 683 rows show > 100% load - mostly the suspect IPCs above. A clean machine cannot exceed 100% of its rated frequency on average.

### 3.7 Per-factory distributions

Factory 5 stands out:

| Factory | n rows | mean AvgValue | std | max |
|---|---|---|---|---|
| 1 | 54,711 | 704 | 1,620 | 23,061 |
| 2 | 45,021 | 795 | 1,284 | 15,875 |
| 3 | 61,978 | 589 | 1,216 | 16,795 |
| 4 | 33,901 | 546 | 1,034 | 10,876 |
| **5** | 24,683 | **2,566** | **17,026** | **349,704** |

Without `ITLT1593`, factory 5 looks similar to the others.

### 3.8 Weekday pattern

A small dip on Thursday (median 240) vs ~260 elsewhere. The differences are minor and partly driven by uneven row counts per weekday - real, but probably not a top-3 feature for a model.

---

## 4. How to read the notebook charts (`eda_v5.ipynb`)

| Section | Chart | What to look for |
|---|---|---|
| 2. Histograms | Linear vs log10 | Linear histograms look "all in one bar" because of the long tail; log views show that values span ~5 orders of magnitude. |
| 3. Boxplots by Factory | Raw vs log | The raw plot is dominated by factory 5 outliers; the log plot reveals the actual factory-to-factory difference is modest. |
| 4. Correlation matrix | Pearson + Spearman | Pearson is distorted by the heavy tail; Spearman is the trustworthy one. Expect very high (>0.9) rank correlation between `Avg`, `Min`, `Max`. |
| 5. Pairplot | log10 sample | Color-by-factory shows whether factories occupy distinct regions in feature space. |
| 6. Time series | Daily mean & median | Mean is jumpy (outlier-sensitive), median is stable - confirms the outlier story. The "rows per day" plot reveals 2021-06-28 is sparse. |
| 7. Weekday | Median + log boxplot | Confirms the small Thursday dip without outlier distortion. |
| 8. CpuMHz / LoadPct | Catalog + histogram | CpuMHz is multi-modal (a handful of common machine classes); LoadPct hist clipped at 200% with 100% reference line shows how many points are physically impossible. |
| 9. Top noisy IPCs | Tables + ITLT1593 series | Identifies which machines drive the tail. The ITLT1593 line plot makes the 30x-rated anomaly visually obvious. |

---

## 5. Recommendations for downstream work

1. **Drop `MetricId`** - it is constant.
2. **Decide a policy for composite `CpuMHz`** - split into multiple rows, take the max, or sum. Currently the LoadPct uses the first token, which is convenient but arbitrary.
3. **Treat suspect IPCs** (especially `ITLT1593`) as data errors. Either exclude them or cap values at `CpuMHz_num`.
4. **Use log transforms or robust scalers** for `AvgValue`, `MinValue`, `MaxValue` - they span 5+ orders of magnitude.
5. **Drop redundant features** - `Min`, `Avg`, `Max` are near-collinear (rank corr > 0.9). Keep `Avg` and the derived `Range = Max - Min`.
6. **Handle irregular time coverage** - aggregate to weekly, pad missing days, or use models that tolerate gaps. Median per-IPC coverage is 54/61 days.
7. **Prefer `LoadPct` over raw MHz** if comparing across machines - normalises away CPU class differences.

---

## 6. File map

```
Assignment/
  Database - Testcase_agentic_ai_V1.0.zip.csv   (input)
  eda_v1.py    initial format discovery (intentionally fails)
  eda_v2.py    schema and value counts
  eda_v3.py    integrity, coverage, outliers (Unicode crash)
  eda_v4.py    ASCII rerun - canonical tabular EDA
  eda_v5.ipynb visual notebook
  eda_explanation_v1.md   this document
```

Each script is self-contained: open it, hit run, no arguments.

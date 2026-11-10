"""Phase 0 data audit over the raw RCAEval downloads.

Writes:
  results/audit_cases.csv     one row per case: dataset, system, service, fault, rep, files, sizes, rows, time units
  results/audit_columns.csv   one row per (dataset, file): column list as seen in the first case and how many cases share it
  results/audit_summary.csv   one row per dataset: counts, modality presence, parent-span field, size stats
  results/audit_stray_files.csv  entries next to the repetition folders that are not cases
"""
from __future__ import annotations

import csv
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.adapter.layout import list_raw_cases, parse_folder  # noqa: E402
from rca.paths import DATASETS, RAW_DIR, RESULTS_DIR  # noqa: E402

MODALITY_FILES = {
    "metrics": ["data.csv", "simple_data.csv", "metrics.csv", "simple_metrics.csv"],
    "logs": ["logs.csv"],
    "traces": ["traces.csv"],
}


STRAY: list[dict] = []


def list_cases(dataset: str) -> list[Path]:
    """Cases are numbered repetition folders under <service>_<fault>/. Anything else is recorded as stray."""
    cases, stray = list_raw_cases(dataset)
    STRAY.extend({"dataset": dataset, "path": s} for s in stray)
    return cases


def header(path: Path) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return next(csv.reader(f))


def count_rows(path: Path) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f) - 1


def time_unit(values: pd.Series) -> str:
    v = pd.to_numeric(values, errors="coerce").dropna()
    if v.empty:
        return "non-numeric"
    m = float(v.median())
    for unit, lo, hi in [("s", 1e9, 1e10), ("ms", 1e12, 1e13), ("us", 1e15, 1e16), ("ns", 1e18, 1e19)]:
        if lo <= m < hi:
            return unit
    return f"unknown(median={m:.3g})"


def audit_case(dataset: str, case: Path) -> dict:
    sf = case.parent.name
    parsed = parse_folder(sf)
    files = sorted(p.name for p in case.iterdir() if p.is_file())
    row = {
        "dataset": dataset,
        "system": dataset.split("-")[1],
        "case_dir": f"{sf}/{case.name}",
        "gt_service": parsed["service"],
        "gt_fault": parsed["fault"],
        "folder_variant": parsed["variant"],
        "rep": case.name,
        "files": ";".join(files),
        "size_mb": round(sum((case / f).stat().st_size for f in files) / 1e6, 2),
    }
    inj = case / "inject_time.txt"
    row["inject_time_raw"] = inj.read_text().strip() if inj.exists() else ""
    row["inject_time_unit"] = time_unit(pd.Series([row["inject_time_raw"]])) if row["inject_time_raw"] else "missing"
    for mod, names in MODALITY_FILES.items():
        present = [n for n in names if n in files]
        row[f"has_{mod}"] = bool(present)
        row[f"{mod}_files"] = ";".join(present)
    metric_file = next((n for n in ["metrics.csv", "data.csv", "simple_metrics.csv", "simple_data.csv"] if n in files), None)
    if metric_file:
        cols = header(case / metric_file)[1:]
        row["metric_entities"] = ";".join(sorted({c.split("_")[0] for c in cols if c != "time"}))
        df = pd.read_csv(case / metric_file, usecols=[0])
        tcol = df.iloc[:, 0]
        row["metric_rows"] = len(df)
        row["metric_cols"] = len(header(case / metric_file)) - 1
        row["metric_time_unit"] = time_unit(tcol)
        t = pd.to_numeric(tcol, errors="coerce").dropna()
        row["metric_step_s"] = float(t.diff().median()) if len(t) > 1 else None
        row["metric_span_min"] = round(float(t.max() - t.min()) / 60, 2) if len(t) else None
        if row["inject_time_raw"]:
            it = float(row["inject_time_raw"])
            row["pre_fault_min"] = round((it - float(t.min())) / 60, 2)
            row["post_fault_min"] = round((float(t.max()) - it) / 60, 2)
    if "traces.csv" in files:
        cols = header(case / "traces.csv")
        row["trace_cols"] = ";".join(cols)
        row["trace_has_parent"] = any("parent" in c.lower() for c in cols)
        row["trace_rows"] = count_rows(case / "traces.csv")
        sample = pd.read_csv(case / "traces.csv", nrows=2000)
        for c in ("startTime", "startTimeMillis", "duration"):
            if c in sample:
                row[f"trace_{c}_unit"] = time_unit(sample[c]) if c != "duration" else f"median={sample[c].median()}"
        sv = pd.read_csv(case / "traces.csv", usecols=lambda c: c in ("serviceName", "statusCode", "parentSpanID", "spanID"))
        row["trace_services"] = ";".join(sorted(sv["serviceName"].dropna().astype(str).unique()))
        row["trace_status_values"] = ";".join(str(v) for v in sv["statusCode"].value_counts(dropna=False).head(8).index)
        if "parentSpanID" in sv:
            row["trace_root_spans"] = int(sv["parentSpanID"].isna().sum())
            row["trace_parent_missing_in_case"] = int((sv["parentSpanID"].notna() & ~sv["parentSpanID"].isin(sv["spanID"])).sum())
    if "logs.csv" in files:
        cols = header(case / "logs.csv")
        row["log_cols"] = ";".join(cols)
        row["log_rows"] = count_rows(case / "logs.csv")
        sample = pd.read_csv(case / "logs.csv", nrows=2000)
        if "timestamp" in sample:
            row["log_timestamp_unit"] = time_unit(sample["timestamp"])
        row["log_has_span_id"] = any("span" in c.lower() for c in cols)
    return row


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    rows = []
    col_seen: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for ds in DATASETS:
        if not (RAW_DIR / ds).exists():
            print(f"missing dataset folder {ds}")
            continue
        cases = list_cases(ds)
        print(ds, len(cases), "cases", flush=True)
        for c in cases:
            rows.append(audit_case(ds, c))
            for f in c.iterdir():
                if f.suffix == ".csv":
                    col_seen[(ds, f.name)][";".join(header(f))] += 1
    cases_df = pd.DataFrame(rows)
    cases_df.to_csv(RESULTS_DIR / "audit_cases.csv", index=False)

    col_rows = []
    for (ds, fname), cnt in sorted(col_seen.items()):
        for cols, n in cnt.most_common():
            col_rows.append({"dataset": ds, "file": fname, "n_cases": n, "n_cols": len(cols.split(";")),
                             "columns": cols if len(cols) < 3000 else cols[:3000] + "...(truncated)"})
    pd.DataFrame(col_rows).to_csv(RESULTS_DIR / "audit_columns.csv", index=False)

    summ = []
    for ds, g in cases_df.groupby("dataset", sort=False):
        summ.append({
            "dataset": ds,
            "cases": len(g),
            "services_injected": g["gt_service"].nunique(),
            "faults": ";".join(sorted(g["gt_fault"].unique())),
            "cases_with_metrics": int(g["has_metrics"].sum()),
            "cases_with_logs": int(g["has_logs"].sum()),
            "cases_with_traces": int(g["has_traces"].sum()),
            "cases_with_parent_span": int(g.get("trace_has_parent", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
            "cases_with_inject_time": int((g["inject_time_unit"] != "missing").sum()),
            "inject_time_units": ";".join(sorted(g["inject_time_unit"].unique())),
            "metric_time_units": ";".join(sorted(g["metric_time_unit"].dropna().unique())),
            "metric_step_s_median": g["metric_step_s"].median(),
            "metric_cols_min": g["metric_cols"].min(),
            "metric_cols_max": g["metric_cols"].max(),
            "pre_fault_min_median": g["pre_fault_min"].median(),
            "post_fault_min_median": g["post_fault_min"].median(),
            "size_mb_min": g["size_mb"].min(),
            "size_mb_median": g["size_mb"].median(),
            "size_mb_max": g["size_mb"].max(),
            "size_mb_total": round(g["size_mb"].sum(), 1),
        })
    pd.DataFrame(summ).to_csv(RESULTS_DIR / "audit_summary.csv", index=False)
    pd.DataFrame(STRAY, columns=["dataset", "path"]).to_csv(RESULTS_DIR / "audit_stray_files.csv", index=False)
    print(pd.DataFrame(summ).to_string())


if __name__ == "__main__":
    main()

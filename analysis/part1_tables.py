"""Part 1 tables (SPEC Phase 5 steps 6-7). Every number in PART1_REPORT.md comes from these CSVs.

Inputs: the test runs (3 per configuration), the onset run, results/control.csv, results/code_ceiling_test.csv.
Outputs (results/):
  runs.csv                    one row per (run, case): the SPEC 5.6 columns
  part1_summary.csv           AC@1/3/5, Avg@5 per dataset / system / fault type, service and indicator level,
                              V3, V4 (mean and sd over runs) and the control on the same cases
  part1_accuracy_per_run.csv  the same per run
  part1_fault_type.csv        fault-type accuracy per dataset and class
  part1_confusion.csv         fault-type confusion matrix (true x predicted)
  part1_calibration.csv       reliability bins and Brier score per dataset
  part1_stability.csv         per-case agreement of top-1 across runs; accuracy spread across runs
  part1_cost.csv              cost, tokens, latency per case, per dataset
  part1_guardrails.csv        rejections by reason, limit hits, forced reports, crashes, per dataset
  part1_ceiling_vs_system.csv code-only ceiling vs system top-5 on trace-bearing test cases
  part1_onset.csv             onset-detection run vs provided-time runs on the same cases

Usage: python analysis/part1_tables.py --runs test_r1 test_r2 test_r3 --onset test_onset
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RESULTS_DIR, RUNS_DIR, SPLITS_CSV  # noqa: E402
from rca.scoring import gt_service_key, hit_at, score_cases  # noqa: E402
from rca.truth import load_truth  # noqa: E402

FAULT_VOCAB = {"cpu": "cpu", "mem": "memory", "disk": "disk", "socket": "socket", "delay": "delay", "loss": "loss",
               "f1": "code", "f2": "code", "f3": "code", "f4": "code", "f5": "code"}
METRICS = ["AC@1", "AC@3", "AC@5", "Avg@5"]


def load_runs(run_ids: list[str]) -> pd.DataFrame:
    rows = []
    for rid in run_ids:
        for line in open(RUNS_DIR / rid / "results.jsonl"):
            rows.append(json.loads(line))
    df = pd.DataFrame(rows).drop_duplicates(["run_id", "case_id"], keep="last")
    sp = pd.read_csv(SPLITS_CSV)
    df = df.merge(sp[["case_id", "system", "split"]], on="case_id", how="left")
    t = {(d, c): load_truth(d, c) for d, c in zip(df["dataset"], df["case_id"])}
    df["gt_service"] = [t[k]["gt_service"] for k in zip(df["dataset"], df["case_id"])]
    df["gt_fault_type"] = [t[k]["gt_fault_type"] for k in zip(df["dataset"], df["case_id"])]
    df["has_ranking"] = df["ranked_v3"].map(lambda r: isinstance(r, list) and len(r) > 0)
    return df


def score_group(g: pd.DataFrame, col: str, level: str) -> dict:
    rows = [{"ranked": (r if level == "service" else ind), "gt_service": s, "fault": f, "dataset": d}
            for r, ind, s, f, d in zip(g[col], g["ranked_indicators"], g["gt_service"], g["gt_fault_type"], g["dataset"])
            if isinstance(r, list)]
    return score_cases(rows, level)


def accuracy_tables(df: pd.DataFrame, control: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    per_run = []
    keys = [("dataset", None), ("system", None), ("fault", "gt_fault_type"), ("dataset_fault", None)]
    for run_id, r in df.groupby("run_id"):
        r = r[r["has_ranking"]]
        groupings = [("ALL", "ALL", r)] + [("dataset", k, g) for k, g in r.groupby("dataset")] \
            + [("system", k, g) for k, g in r.groupby("system")] \
            + [("fault_type", k, g) for k, g in r.groupby("gt_fault_type")] \
            + [("dataset x fault_type", f"{a}|{b}", g) for (a, b), g in r.groupby(["dataset", "gt_fault_type"])]
        for by, key, g in groupings:
            for variant, col in [("V3", "ranked_v3"), ("V4", "ranked_v4")]:
                for level in ("service", "indicator"):
                    if level == "indicator" and variant == "V4":
                        continue  # the gate reorders services only; indicators are the agent's
                    sc = score_group(g, col, level)
                    if not sc.get("n"):
                        continue
                    per_run.append({"run_id": run_id, "by": by, "group": key, "variant": variant, "level": level,
                                    "n": sc["n"], **{m: sc[m] for m in METRICS}})
    pr = pd.DataFrame(per_run)
    summ = pr.groupby(["by", "group", "variant", "level"]).agg(
        n_cases=("n", "max"), n_runs=("run_id", "nunique"),
        **{f"{m}_mean": (m, "mean") for m in METRICS}, **{f"{m}_sd": (m, "std") for m in METRICS}).reset_index()
    # control on the same cases (deterministic, one run)
    cases = df.drop_duplicates("case_id")[["case_id", "dataset", "system", "gt_fault_type", "gt_service"]]
    c = cases.merge(control[["case_id", "ranked_top10"]], on="case_id")
    c["ranked"] = c["ranked_top10"].map(json.loads)
    crow = []
    groupings = [("ALL", "ALL", c)] + [("dataset", k, g) for k, g in c.groupby("dataset")] \
        + [("system", k, g) for k, g in c.groupby("system")] + [("fault_type", k, g) for k, g in c.groupby("gt_fault_type")] \
        + [("dataset x fault_type", f"{a}|{b}", g) for (a, b), g in c.groupby(["dataset", "gt_fault_type"])]
    for by, key, g in groupings:
        sc = score_cases([{"ranked": r, "gt_service": s, "fault": f, "dataset": d}
                          for r, s, f, d in zip(g["ranked"], g["gt_service"], g["gt_fault_type"], g["dataset"])], "service")
        crow.append({"by": by, "group": key, "variant": "control (reference)", "level": "service", "n_cases": sc["n"],
                     "n_runs": 1, **{f"{m}_mean": sc[m] for m in METRICS}})
    summ = pd.concat([summ, pd.DataFrame(crow)], ignore_index=True)
    return summ, pr


def fault_type_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = df[df["has_ranking"]].copy()
    d["true_ft"] = d["gt_fault_type"].map(FAULT_VOCAB)
    d["pred_ft"] = d["fault_type"].fillna("unknown")
    d["correct"] = d["true_ft"] == d["pred_ft"]
    acc = []
    for by, groups in [("ALL", [("ALL", d)]), ("dataset", list(d.groupby("dataset"))), ("class", list(d.groupby("true_ft"))),
                       ("dataset x class", [(f"{a}|{b}", g) for (a, b), g in d.groupby(["dataset", "true_ft"])])]:
        for key, g in groups:
            per_run = g.groupby("run_id")["correct"].mean()
            acc.append({"by": by, "group": key, "n_rows": len(g), "accuracy_mean": per_run.mean(), "accuracy_sd": per_run.std(),
                        "share_unknown": (g["pred_ft"] == "unknown").mean()})
    conf = pd.crosstab(d["true_ft"], d["pred_ft"]).reset_index()
    return pd.DataFrame(acc), conf


def calibration_table(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["has_ranking"]].copy()
    d["correct"] = [hit_at(r, g, 1) for r, g in zip(d["ranked_v4"], d["gt_service"])]
    out = []
    bins = np.linspace(0, 1, 11)
    for key, g in [("ALL", d)] + list(d.groupby("dataset")):
        brier = float(((g["confidence"] - g["correct"].astype(float)) ** 2).mean())
        out.append({"dataset": key, "bin": "ALL", "n": len(g), "mean_confidence": g["confidence"].mean(),
                    "accuracy": g["correct"].mean(), "brier": brier})
        g = g.assign(b=pd.cut(g["confidence"], bins, include_lowest=True))
        for b, gb in g.groupby("b", observed=True):
            out.append({"dataset": key, "bin": str(b), "n": len(gb), "mean_confidence": gb["confidence"].mean(),
                        "accuracy": gb["correct"].mean(), "brier": None})
    return pd.DataFrame(out)


def stability_table(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["has_ranking"]].copy()
    d["top1"] = d["ranked_v3"].map(lambda r: r[0])
    out = []
    for key, g in [("ALL", d)] + list(d.groupby("dataset")):
        per_case = g.groupby("case_id")["top1"].agg(lambda x: Counter(x).most_common(1)[0][1] / len(x))
        n_runs = g.groupby("case_id")["run_id"].nunique()
        acc = g.assign(h=[hit_at(r, s, 1) for r, s in zip(g["ranked_v3"], g["gt_service"])]).groupby("run_id")["h"].mean()
        out.append({"dataset": key, "n_cases": len(per_case), "runs_per_case_min": int(n_runs.min()),
                    "mean_top1_agreement": per_case.mean(), "share_cases_all_runs_agree": (per_case == 1).mean(),
                    "acc1_min_run": acc.min(), "acc1_max_run": acc.max(), "acc1_spread": acc.max() - acc.min(),
                    "acc1_sd_runs": acc.std()})
    return pd.DataFrame(out)


def cost_table(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for key, g in [("ALL", df)] + list(df.groupby("dataset")):
        out.append({"dataset": key, "n_rows": len(g), "cost_usd_mean": g["cost_usd"].mean(), "cost_usd_total": g["cost_usd"].sum(),
                    "prompt_tokens_mean": g["prompt_tokens"].mean(), "completion_tokens_mean": g["completion_tokens"].mean(),
                    "latency_s_mean": g["latency_s"].mean(), "latency_s_p90": g["latency_s"].quantile(0.9),
                    "llm_calls_mean": g["llm_calls"].mean(), "subagent_launches_mean": g["subagent_launches"].mean()})
    return pd.DataFrame(out)


def guardrail_table(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for key, g in [("ALL", df)] + list(df.groupby("dataset")):
        reasons = Counter(r for rr in g["rejection_reasons"].dropna() for r in rr)
        limits = Counter(l for ll in g["limits_hit"].dropna() for l in ll)
        row = {"dataset": key, "n_rows": len(g), "rows_with_rejection": int((g["guardrail_rejections"] > 0).sum()),
               "rejections_total": int(g["guardrail_rejections"].sum()),
               "report_accepted": int((g["report_status"] == "accepted").sum()),
               "report_forced": int((g["report_status"] == "forced").sum()),
               "report_none": int((g["report_status"] == "none").sum()),
               "status_crash": int(g["status"].astype(str).str.startswith("crash").sum()),
               "status_limit_hit": int((g["status"] == "limit_hit").sum())}
        row.update({f"reason_{k}": v for k, v in reasons.items()})
        row.update({f"limit_{k}": v for k, v in limits.items()})
        out.append(row)
    return pd.DataFrame(out).fillna(0)


def ceiling_table(df: pd.DataFrame) -> pd.DataFrame | None:
    p = RESULTS_DIR / "code_ceiling_test.csv"
    if not p.exists():
        return None
    ce = pd.read_csv(p)
    ce = ce[ce["case_id"] != "SUMMARY"][["case_id", "gt_flagged", "gt_in_top5"]]
    ce["gt_flagged"] = ce["gt_flagged"].astype(str) == "True"
    d = df[df["has_ranking"]].merge(ce, on="case_id")
    d["sys_top5"] = [hit_at(r, g, 5) for r, g in zip(d["ranked_v3"], d["gt_service"])]
    d["sys_top1"] = [hit_at(r, g, 1) for r, g in zip(d["ranked_v3"], d["gt_service"])]
    out = []
    for key, g in [("ALL", d)] + list(d.groupby("dataset")):
        out.append({"dataset": key, "n_rows": len(g), "code_flags_gt": g["gt_flagged"].mean(), "system_top5": g["sys_top5"].mean(),
                    "system_top1": g["sys_top1"].mean(),
                    "code_flagged_but_system_missed_top5": (g["gt_flagged"] & ~g["sys_top5"]).mean(),
                    "system_found_top5_code_did_not_flag": (~g["gt_flagged"] & g["sys_top5"]).mean()})
    return pd.DataFrame(out)


def onset_table(df: pd.DataFrame, onset: pd.DataFrame) -> pd.DataFrame:
    o = onset[onset["has_ranking"]]
    cases = set(o["case_id"])
    p = df[df["case_id"].isin(cases) & df["has_ranking"]]
    out = []
    for name, g in [("provided (all test runs)", p), ("detected onset", o)]:
        for key, gg in [("ALL", g)] + list(g.groupby("dataset")):
            sc = score_group(gg, "ranked_v3", "service")
            out.append({"fault_time": name, "dataset": key, "n_rows": len(gg), **{m: sc.get(m) for m in METRICS}})
    return pd.DataFrame(out)


def onset_error(onset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    from rca.tools.data import CaseData

    for d, c, on in zip(onset["dataset"], onset["case_id"], onset["onset"]):
        if not isinstance(on, dict):
            continue
        true_t = CaseData(d, c).case["fault_start"]
        rows.append({"dataset": d, "case_id": c, "detected_minus_true_s": on["detected_onset"] - true_t, "found": on["found"]})
    e = pd.DataFrame(rows)
    out = []
    for key, g in [("ALL", e)] + list(e.groupby("dataset")):
        out.append({"fault_time": "onset error", "dataset": key, "n_rows": len(g),
                    "median_abs_error_s": g["detected_minus_true_s"].abs().median(),
                    "share_within_60s": (g["detected_minus_true_s"].abs() <= 60).mean(), "share_found": g["found"].mean()})
    return pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--onset", default=None)
    args = ap.parse_args()
    df = load_runs(args.runs)
    if (df["split"] != "test").any():
        raise SystemExit("part1 tables are for test runs only")
    df["run"] = df["run_id"]
    runs_csv = df[["dataset", "case_id", "run", "ranked_v3", "ranked_v4", "ranked_indicators", "fault_type", "confidence",
                   "gate_path", "cost_usd", "prompt_tokens", "completion_tokens", "latency_s", "limits_hit",
                   "guardrail_rejections", "rejection_reasons", "status", "report_status"]].copy()
    for c in ("ranked_v3", "ranked_v4", "ranked_indicators", "limits_hit", "rejection_reasons"):
        runs_csv[c] = runs_csv[c].map(json.dumps)
    runs_csv.to_csv(RESULTS_DIR / "runs.csv", index=False)

    control = pd.read_csv(RESULTS_DIR / "control.csv")
    summ, per_run = accuracy_tables(df, control)
    summ.to_csv(RESULTS_DIR / "part1_summary.csv", index=False)
    per_run.to_csv(RESULTS_DIR / "part1_accuracy_per_run.csv", index=False)
    ft, conf = fault_type_tables(df)
    ft.to_csv(RESULTS_DIR / "part1_fault_type.csv", index=False)
    conf.to_csv(RESULTS_DIR / "part1_confusion.csv", index=False)
    calibration_table(df).to_csv(RESULTS_DIR / "part1_calibration.csv", index=False)
    stability_table(df).to_csv(RESULTS_DIR / "part1_stability.csv", index=False)
    cost_table(df).to_csv(RESULTS_DIR / "part1_cost.csv", index=False)
    guardrail_table(df).to_csv(RESULTS_DIR / "part1_guardrails.csv", index=False)
    ce = ceiling_table(df)
    if ce is not None:
        ce.to_csv(RESULTS_DIR / "part1_ceiling_vs_system.csv", index=False)
    if args.onset:
        on = load_runs([args.onset])
        pd.concat([onset_table(df, on), onset_error(on)], ignore_index=True).to_csv(RESULTS_DIR / "part1_onset.csv", index=False)
    print(summ[(summ["by"].isin(["ALL", "dataset"])) & (summ["level"] == "service")].to_string())


if __name__ == "__main__":
    main()

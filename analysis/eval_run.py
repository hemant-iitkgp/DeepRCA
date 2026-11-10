"""Score one or more runs with RCAEval's Evaluator and summarise run health.

Writes results/eval_<tag>_cases.csv (one row per case and run) and results/eval_<tag>_summary.csv
(per dataset: AC@1/3/5, Avg@5 for V3, V4 and the control on the same cases; completion, cost,
latency, limit hits, rejections).

Usage: python analysis/eval_run.py --runs dev_v1 --tag dev_v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RESULTS_DIR, RUNS_DIR  # noqa: E402
from rca.scoring import gt_service_key, hit_at, score_cases  # noqa: E402
from rca.truth import load_truth  # noqa: E402


def load(run_ids: list[str]) -> pd.DataFrame:
    rows = []
    for rid in run_ids:
        p = RUNS_DIR / rid / "results.jsonl"
        for line in open(p):
            rows.append(json.loads(line))
    df = pd.DataFrame(rows).drop_duplicates(["run_id", "case_id"], keep="last")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    df = load(args.runs)
    truth = {(d, c): load_truth(d, c) for d, c in zip(df["dataset"], df["case_id"])}
    df["gt_service"] = [truth[(d, c)]["gt_service"] for d, c in zip(df["dataset"], df["case_id"])]
    df["gt_fault_type"] = [truth[(d, c)]["gt_fault_type"] for d, c in zip(df["dataset"], df["case_id"])]
    ok = df["ranked_v3"].notna() if "ranked_v3" in df else pd.Series(False, index=df.index)
    for col, name in [("ranked_v3", "v3"), ("ranked_v4", "v4")]:
        for k in (1, 3, 5):
            df[f"{name}_hit{k}"] = [hit_at(r, g, k) if isinstance(r, list) else False for r, g in zip(df.get(col), df["gt_service"])]
    df["control_hit1"] = [gt_service_key(str(t)) == gt_service_key(g) for t, g in zip(df.get("control_top1"), df["gt_service"])]
    df["symptom_aligned"] = df["control_hit1"]
    keep = [c for c in ["run_id", "dataset", "case_id", "status", "report_status", "gt_service", "gt_fault_type",
                        "fault_type", "control_top1", "symptom_aligned", "v3_hit1", "v3_hit3", "v3_hit5", "v4_hit1",
                        "v4_hit3", "v4_hit5", "gate_path", "confidence", "critic_verdict", "top1_positive_evidence",
                        "cost_usd", "prompt_tokens", "completion_tokens", "latency_s", "subagent_launches",
                        "limits_hit", "guardrail_rejections", "rejection_reasons", "work_items", "work_items_covered",
                        "ranked_v3", "ranked_v4"] if c in df]
    df[keep].to_csv(RESULTS_DIR / f"eval_{args.tag}_cases.csv", index=False)

    summ = []
    groups = [("ALL", df)] + list(df.groupby("dataset"))
    for ds, g in groups:
        g_ok = g[g["ranked_v3"].map(lambda r: isinstance(r, list))]
        row = {"dataset": ds, "n_rows": len(g), "n_runs": g["run_id"].nunique(),
               "completed_ok": int((g["status"] == "ok").sum()), "crashed": int(g["status"].astype(str).str.startswith("crash").sum()),
               "limit_hit": int((g["status"] == "limit_hit").sum()),
               "report_accepted": int((g.get("report_status") == "accepted").sum()),
               "report_forced": int((g.get("report_status") == "forced").sum()),
               "report_none": int((g.get("report_status") == "none").sum()),
               "mean_cost_usd": g["cost_usd"].mean(), "mean_latency_s": g["latency_s"].mean(),
               "mean_launches": g["subagent_launches"].mean(), "mean_rejections": g["guardrail_rejections"].mean(),
               "symptom_aligned_share": g["symptom_aligned"].mean()}
        for col, name in [("ranked_v3", "v3"), ("ranked_v4", "v4")]:
            sc = score_cases([{"ranked": r, "gt_service": s, "fault": f, "dataset": d} for r, s, f, d in
                              zip(g_ok[col], g_ok["gt_service"], g_ok["gt_fault_type"], g_ok["dataset"])], "service")
            for k in ("AC@1", "AC@3", "AC@5", "Avg@5"):
                row[f"{name}_{k}"] = sc.get(k)
        row["control_AC@1"] = g["control_hit1"].mean()
        al, mis = g_ok[g_ok["symptom_aligned"]], g_ok[~g_ok["symptom_aligned"]]
        row["v3_acc_aligned"] = al["v3_hit1"].mean() if len(al) else None
        row["v3_acc_misleading"] = mis["v3_hit1"].mean() if len(mis) else None
        row["v4_acc_aligned"] = al["v4_hit1"].mean() if len(al) else None
        row["v4_acc_misleading"] = mis["v4_hit1"].mean() if len(mis) else None
        row["n_aligned"], row["n_misleading"] = len(al), len(mis)
        summ.append(row)
    s = pd.DataFrame(summ)
    s.to_csv(RESULTS_DIR / f"eval_{args.tag}_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(s.T.to_string())


if __name__ == "__main__":
    main()

"""Score the test cases finished so far (by wave) for a partial Part 1 report.

Reads every runs/<run_id>/<case_id>/result.json for the given test run (the per-case files are the source of
truth; results.jsonl may hold duplicate or interleaved lines when two projects run in parallel), restricted to
the requested waves. Scores with RCAEval's Evaluator (rca.scoring) and writes:
  results/wave_<tag>_cases.csv     one row per case
  results/wave_<tag>_accuracy.csv  AC@1/3/5, Avg@5 per dataset / system / fault type, system (V3, V4) vs control,
                                   exact McNemar p on the discordant pairs (fixed vs broken),
                                   with 95% bootstrap CIs (10,000 resamples over cases) for AC@1 and the difference
  results/wave_<tag>_ops.csv       completion, guardrail, fault type, cost, latency, tokens per dataset

Usage: python analysis/wave_report.py --run test_r1 --waves 1 --tag w1_r1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import DATA_DIR, RESULTS_DIR, RUNS_DIR  # noqa: E402
from rca.scoring import gt_service_key, hit_at, score_cases  # noqa: E402
from rca.truth import load_truth  # noqa: E402

FAULT_VOCAB = {"cpu": "cpu", "mem": "memory", "disk": "disk", "socket": "socket", "delay": "delay", "loss": "loss",
               "f1": "code", "f2": "code", "f3": "code", "f4": "code", "f5": "code"}
RNG = np.random.default_rng(7)


def boot_ci(x: np.ndarray, n: int = 10000) -> tuple[float, float]:
    if len(x) == 0:
        return (np.nan, np.nan)
    idx = RNG.integers(0, len(x), size=(n, len(x)))
    m = x[idx].mean(axis=1)
    return float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


def load(run_id: str, waves: list[int]) -> pd.DataFrame:
    w = pd.read_csv(DATA_DIR / "test_waves.csv")
    w = w[w["wave"].isin(waves)]
    ctrl = pd.read_csv(RESULTS_DIR / "control.csv").set_index("case_id")
    rows = []
    for r in w.itertuples():
        p = RUNS_DIR / run_id / r.case_id / "result.json"
        base = {"case_id": r.case_id, "dataset": r.dataset, "system": r.system, "wave": r.wave}
        t = load_truth(r.dataset, r.case_id)
        base.update(gt_service=t["gt_service"], gt_fault_type=t["gt_fault_type"],
                    control_ranked=json.loads(ctrl.loc[r.case_id, "ranked_top10"]))
        if not p.exists():
            rows.append({**base, "finished": False})
            continue
        res = json.loads(p.read_text())
        rows.append({**base, "finished": True, **{k: res.get(k) for k in (
            "status", "report_status", "ranked_v3", "ranked_v4", "ranked_indicators", "fault_type", "confidence",
            "gate_path", "cost_usd", "prompt_tokens", "completion_tokens", "latency_s", "subagent_launches",
            "guardrail_rejections", "rejection_reasons", "limits_hit", "gcp_project", "malformed_retries")}})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--waves", nargs="+", type=int, required=True)
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    df = load(args.run, args.waves)
    if "ranked_v3" not in df:
        print(f"no finished cases yet ({len(df)} in the selected waves)")
        return
    fin = df[df["finished"] & df["ranked_v3"].map(lambda r: isinstance(r, list))].copy()
    for k in (1, 3, 5):
        fin[f"v3_hit{k}"] = [hit_at(r, g, k) for r, g in zip(fin["ranked_v3"], fin["gt_service"])]
        fin[f"control_hit{k}"] = [hit_at(r, g, k) for r, g in zip(fin["control_ranked"], fin["gt_service"])]
    fin["symptom_aligned"] = fin["control_hit1"]
    fin["true_fault_class"] = fin["gt_fault_type"].map(FAULT_VOCAB)
    fin["fault_type_correct"] = fin["true_fault_class"] == fin["fault_type"]
    out_cases = fin.drop(columns=["control_ranked"]).copy()
    for c in ("ranked_v3", "ranked_v4", "ranked_indicators", "rejection_reasons", "limits_hit"):
        out_cases[c] = out_cases[c].map(json.dumps)
    out_cases.to_csv(RESULTS_DIR / f"wave_{args.tag}_cases.csv", index=False)

    acc = []
    groups = [("ALL", "ALL", fin)] + [("dataset", k, g) for k, g in fin.groupby("dataset")] \
        + [("system", k, g) for k, g in fin.groupby("system")] \
        + [("fault_type", k, g) for k, g in fin.groupby("true_fault_class")] \
        + [("stratum", k, g) for k, g in fin.groupby(np.where(fin["symptom_aligned"], "aligned", "misleading"))]
    for by, key, g in groups:
        rows = lambda col: [{"ranked": r, "gt_service": s, "fault": f, "dataset": d}  # noqa: E731
                            for r, s, f, d in zip(g[col], g["gt_service"], g["gt_fault_type"], g["dataset"])]
        s3, sc = score_cases(rows("ranked_v3"), "service"), score_cases(rows("control_ranked"), "service")
        s4 = score_cases(rows("ranked_v4"), "service")
        si = score_cases([{"ranked": r, "gt_service": s, "fault": f, "dataset": d} for r, s, f, d in
                          zip(g["ranked_indicators"], g["gt_service"], g["gt_fault_type"], g["dataset"])], "indicator")
        h3, hc = g["v3_hit1"].to_numpy(float), g["control_hit1"].to_numpy(float)
        lo, hi = boot_ci(h3)
        dlo, dhi = boot_ci(h3 - hc)
        fixed, broken = int(((h3 == 1) & (hc == 0)).sum()), int(((h3 == 0) & (hc == 1)).sum())
        # exact McNemar: two-sided binomial test on the discordant pairs
        p_mc = binomtest(fixed, fixed + broken, 0.5).pvalue if fixed + broken else np.nan
        acc.append({"by": by, "group": key, "n_cases": len(g),
                    "v3_AC@1": s3["AC@1"], "v3_AC@1_ci_low": lo, "v3_AC@1_ci_high": hi,
                    "v3_AC@3": s3["AC@3"], "v3_AC@5": s3["AC@5"], "v3_Avg@5": s3["Avg@5"],
                    "v4_AC@1": s4["AC@1"], "v4_Avg@5": s4["Avg@5"],
                    "control_AC@1": sc["AC@1"], "control_AC@3": sc["AC@3"], "control_Avg@5": sc["Avg@5"],
                    "diff_AC@1": s3["AC@1"] - sc["AC@1"], "diff_ci_low": dlo, "diff_ci_high": dhi,
                    "fixed_vs_control": fixed, "broken_vs_control": broken,
                    "indicator_n": si.get("n", 0), "indicator_AC@1": si.get("AC@1"), "indicator_Avg@5": si.get("Avg@5"),
                    "mcnemar_p": p_mc})
    pd.DataFrame(acc).to_csv(RESULTS_DIR / f"wave_{args.tag}_accuracy.csv", index=False)

    ops = []
    for key, g in [("ALL", df)] + list(df.groupby("dataset")):
        f = g[g["finished"]]
        ops.append({"dataset": key, "cases_in_wave": len(g), "finished": int(g["finished"].sum()),
                    "status_ok": int((f["status"] == "ok").sum()), "crash": int(f["status"].astype(str).str.startswith("crash").sum()),
                    "limit_hit": int((f["status"] == "limit_hit").sum()),
                    "report_accepted": int((f["report_status"] == "accepted").sum()),
                    "report_forced": int((f["report_status"] == "forced").sum()),
                    "report_none": int((f["report_status"] == "none").sum()),
                    "fault_type_accuracy": fin.loc[fin["case_id"].isin(f["case_id"]), "fault_type_correct"].mean(),
                    "cost_usd_mean": f["cost_usd"].mean(), "cost_usd_total": f["cost_usd"].sum(),
                    "latency_min_mean": f["latency_s"].mean() / 60, "prompt_tokens_mean": f["prompt_tokens"].mean(),
                    "subagents_mean": f["subagent_launches"].mean(), "rejections_mean": f["guardrail_rejections"].mean(),
                    "confidence_mean": f["confidence"].mean()})
    pd.DataFrame(ops).to_csv(RESULTS_DIR / f"wave_{args.tag}_ops.csv", index=False)
    pd.set_option("display.width", 250)
    print(pd.DataFrame(ops).to_string())
    print(pd.DataFrame(acc)[["by", "group", "n_cases", "v3_AC@1", "v3_AC@1_ci_low", "v3_AC@1_ci_high", "v3_Avg@5",
                             "control_AC@1", "diff_AC@1", "fixed_vs_control", "broken_vs_control", "mcnemar_p"]].round(3).to_string())


if __name__ == "__main__":
    main()

"""Secondary outputs of a scored wave: fault type, confidence and process statistics.

Reads results/wave_<tag>_cases.csv (written by analysis/wave_report.py) and writes:
  results/wave_<tag>_faulttype_confusion.csv  true fault class x predicted fault type (counts)
  results/wave_<tag>_faulttype.csv            fault-type accuracy by true class, dataset, and service hit/miss
  results/wave_<tag>_confidence.csv           calibration bins, plus summary rows (AUROC, Brier, mean by outcome)
  results/wave_<tag>_process.csv              guardrail, retries, gate path, sub-agents, per dataset

Usage: python analysis/wave_extras.py --tag w1_r1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RESULTS_DIR  # noqa: E402

CLASSES = ["cpu", "memory", "disk", "socket", "delay", "loss", "code"]
BINS = [0.0, 0.6, 0.65, 0.7, 0.8, 1.0]


def auroc(score: np.ndarray, label: np.ndarray) -> float:
    """Probability that a correct case gets a higher confidence than a wrong one (ties count half)."""
    pos, neg = score[label], score[~label]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    diff = pos[:, None] - neg[None, :]
    return float(((diff > 0).sum() + 0.5 * (diff == 0).sum()) / diff.size)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    d = pd.read_csv(RESULTS_DIR / f"wave_{args.tag}_cases.csv")
    d["fault_type"] = d["fault_type"].fillna("none")
    d["v3_hit1"] = d["v3_hit1"].astype(bool)

    cols = CLASSES + sorted(set(d["fault_type"]) - set(CLASSES))
    conf = pd.crosstab(d["true_fault_class"], d["fault_type"]).reindex(index=CLASSES, columns=cols, fill_value=0)
    conf.index.name = "true_class"
    conf["n"] = conf.sum(axis=1)
    conf.to_csv(RESULTS_DIR / f"wave_{args.tag}_faulttype_confusion.csv")

    ft = []
    for by, keys in (("true_class", "true_fault_class"), ("dataset", "dataset"), ("service_top1", "v3_hit1")):
        for k, g in d.groupby(keys):
            key = ("service right" if k else "service wrong") if by == "service_top1" else k
            ft.append({"by": by, "group": key, "n_cases": len(g), "fault_type_accuracy": g["fault_type_correct"].mean()})
    for k, g in d.groupby("fault_type"):
        ft.append({"by": "predicted", "group": k, "n_cases": len(g), "fault_type_accuracy": g["fault_type_correct"].mean()})
    ft.append({"by": "ALL", "group": "ALL", "n_cases": len(d), "fault_type_accuracy": d["fault_type_correct"].mean()})
    pd.DataFrame(ft).to_csv(RESULTS_DIR / f"wave_{args.tag}_faulttype.csv", index=False)

    c, y = d["confidence"].to_numpy(float), d["v3_hit1"].to_numpy(bool)
    rows = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = (c >= lo) & (c < hi) if hi < 1.0 else (c >= lo) & (c <= hi)
        rows.append({"row": "bin", "bin": f"{lo:.2f}-{hi:.2f}", "n_cases": int(m.sum()),
                     "mean_confidence": c[m].mean() if m.any() else np.nan, "ac1": y[m].mean() if m.any() else np.nan})
    rows += [{"row": "summary", "bin": "correct top-1", "n_cases": int(y.sum()), "mean_confidence": c[y].mean()},
             {"row": "summary", "bin": "wrong top-1", "n_cases": int((~y).sum()), "mean_confidence": c[~y].mean()},
             {"row": "summary", "bin": "AUROC", "n_cases": len(c), "mean_confidence": auroc(c, y)},
             {"row": "summary", "bin": "Brier", "n_cases": len(c), "mean_confidence": float(((c - y) ** 2).mean())},
             {"row": "summary", "bin": "mean confidence vs AC@1", "n_cases": len(c), "mean_confidence": c.mean(), "ac1": y.mean()}]
    pd.DataFrame(rows).to_csv(RESULTS_DIR / f"wave_{args.tag}_confidence.csv", index=False)

    pr = []
    for k, g in [("ALL", d)] + list(d.groupby("dataset")):
        pr.append({"dataset": k, "n_cases": len(g),
                   "cases_with_rejection": int((g["guardrail_rejections"] > 0).sum()),
                   "rejections_total": int(g["guardrail_rejections"].sum()),
                   "forced_reports": int((g["report_status"] == "forced").sum()),
                   "no_report": int((g["report_status"] == "none").sum()),
                   "malformed_retries_total": int(g["malformed_retries"].sum()),
                   "gate_applied": int((g["gate_path"] != "gate_not_held").sum()),
                   "subagents_mean": g["subagent_launches"].mean(), "subagents_max": int(g["subagent_launches"].max())})
    pd.DataFrame(pr).to_csv(RESULTS_DIR / f"wave_{args.tag}_process.csv", index=False)

    pd.set_option("display.width", 200)
    print(conf.to_string())
    print(pd.DataFrame(ft).round(3).to_string(index=False))
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    print(pd.DataFrame(pr).round(2).to_string(index=False))


if __name__ == "__main__":
    main()

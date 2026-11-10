"""Reference numbers from the RCAEval paper, next to our results on the same dataset.

The RCAEval paper (Pham et al., "RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with
Telemetry Data", WWW'25 Companion, arXiv:2412.17015v2, Table "tab:prelim-1" in 3.framework.tex) reports
baselines only on RE2-TT, per fault type, at service level (coarse-grained). Those numbers are transcribed
below as published. They are reference values from all 90 RE2-TT cases (15 per fault type); they are not
re-scored on our cases (Part 2 re-runs the baselines on the same cases).

Our side is scored here with RCAEval's Evaluator on the RE2-TT test cases finished so far (wave_<tag>_cases.csv)
and the control (control.csv), per fault type and as the paper's AVERAGE column (mean over the six fault types).

Writes:
  results/rcaeval_paper_re2tt.csv        the paper's table, long form
  results/paper_compare_<tag>.csv        paper methods + our V3 and control, AVERAGE and per fault type

Usage: python analysis/paper_reference.py --tag w1_r1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RESULTS_DIR  # noqa: E402
from rca.scoring import score_cases  # noqa: E402

SOURCE = "arXiv:2412.17015v2, Table tab:prelim-1 (RE2-TT, coarse-grained)"
FAULTS = ["cpu", "mem", "disk", "socket", "delay", "loss"]
# method: AC@1, AC@3, Avg@5 for CPU, MEM, DISK, SOCKET, DELAY, LOSS, AVERAGE (as printed)
PAPER = {
    ("Metric", "BARO"): [0.47, 0.8, 0.72, 0.93, 1, 0.99, 1, 1, 1, 0.6, 0.87, 0.83, 0.47, 0.67, 0.63, 0.53, 0.6, 0.64, 0.67, 0.82, 0.8],
    ("Metric", "CausalRCA"): [0.4, 0.63, 0.59, 0.1, 0.27, 0.24, 0.43, 0.83, 0.75, 0.23, 0.5, 0.45, 0.13, 0.23, 0.21, 0.03, 0.37, 0.33, 0.22, 0.47, 0.43],
    ("Metric", "CIRCA"): [0.27, 0.27, 0.28, 0.47, 0.73, 0.68, 0.53, 0.67, 0.64, 0.27, 0.53, 0.52, 0.2, 0.27, 0.28, 0.2, 0.33, 0.35, 0.32, 0.47, 0.46],
    ("Metric", "MicroCause"): [0.19, 0.44, 0.4, 0, 0.09, 0.07, 0.4, 0.4, 0.4, 0, 0.17, 0.15, 0, 0.22, 0.13, 0, 0, 0.07, 0.1, 0.22, 0.2],
    ("Metric", "RCD"): [0.13, 0.13, 0.16, 0.07, 0.07, 0.07, 0, 0.07, 0.05, 0.13, 0.33, 0.29, 0.13, 0.13, 0.15, 0.07, 0.07, 0.07, 0.09, 0.13, 0.13],
    ("Trace", "MicroRank"): [0.21, 0.43, 0.34, 0.25, 0.38, 0.33, 0, 0.36, 0.27, 0.3, 0.4, 0.36, 0.08, 0.31, 0.23, 0.14, 0.36, 0.3, 0.16, 0.37, 0.31],
    ("Trace", "TraceRCA"): [0.64, 0.79, 0.74, 0.63, 0.88, 0.83, 0.64, 0.71, 0.74, 0.6, 0.8, 0.76, 0.85, 0.85, 0.88, 0.57, 0.71, 0.67, 0.66, 0.79, 0.77],
    ("Multi-source", "BARO"): [0.47, 0.8, 0.75, 0.93, 1, 0.99, 1, 1, 1, 0.6, 0.8, 0.79, 0.47, 0.67, 0.61, 0.67, 0.67, 0.71, 0.69, 0.82, 0.81],
    ("Multi-source", "CIRCA"): [0, 0.07, 0.09, 0.07, 0.13, 0.21, 0, 0.07, 0.09, 0.07, 0.13, 0.16, 0.07, 0.07, 0.07, 0.13, 0.2, 0.17, 0.06, 0.11, 0.13],
    ("Multi-source", "PDiagnose"): [0.6, 0.87, 0.81, 0.4, 0.47, 0.48, 0.33, 0.73, 0.69, 0.33, 0.67, 0.6, 0.87, 0.87, 0.87, 0.33, 0.6, 0.57, 0.48, 0.7, 0.67],
    ("Multi-source", "RCD"): [0.17, 0.84, 0.72, 0, 0.44, 0.39, 0.07, 0.76, 0.62, 0.21, 0.77, 0.66, 0.05, 0.28, 0.25, 0.07, 0.75, 0.6, 0.1, 0.64, 0.54],
}


def paper_long() -> pd.DataFrame:
    rows = []
    for (src, m), v in PAPER.items():
        for i, f in enumerate(FAULTS + ["AVERAGE"]):
            rows.append({"source": SOURCE, "data_source": src, "method": m, "fault": f, "n_cases": 90 if f == "AVERAGE" else 15,
                         "AC@1": v[3 * i], "AC@3": v[3 * i + 1], "Avg@5": v[3 * i + 2]})
    return pd.DataFrame(rows)


def ours(tag: str) -> pd.DataFrame:
    cases = pd.read_csv(RESULTS_DIR / f"wave_{tag}_cases.csv")
    cases = cases[cases["dataset"] == "RE2-TT"]
    ctrl = pd.read_csv(RESULTS_DIR / "control.csv").set_index("case_id")
    out = []
    for name, ranked in (("Ours (V3)", cases["ranked_v3"].map(json.loads)),
                         ("Control (z-score)", cases["case_id"].map(lambda c: json.loads(ctrl.loc[c, "ranked_top10"])))):
        per = []
        for f in FAULTS:
            m = (cases["gt_fault_type"] == f).to_numpy()
            rows = [{"ranked": r, "gt_service": g, "fault": f, "dataset": "RE2-TT"}
                    for r, g in zip(ranked[m], cases["gt_service"][m])]
            s = score_cases(rows, "service") if rows else {"n": 0}
            per.append({"data_source": "this work", "method": name, "fault": f, "n_cases": s["n"],
                        "AC@1": s.get("AC@1"), "AC@3": s.get("AC@3"), "Avg@5": s.get("Avg@5")})
        p = pd.DataFrame(per)
        avg = {"data_source": "this work", "method": name, "fault": "AVERAGE", "n_cases": int(p["n_cases"].sum()),
               **{k: p.loc[p["n_cases"] > 0, k].mean() for k in ("AC@1", "AC@3", "Avg@5")}}
        out += per + [avg]
    return pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    paper = paper_long()
    paper.to_csv(RESULTS_DIR / "rcaeval_paper_re2tt.csv", index=False)
    both = pd.concat([ours(args.tag), paper.drop(columns="source")], ignore_index=True)
    both.to_csv(RESULTS_DIR / f"paper_compare_{args.tag}.csv", index=False)
    pd.set_option("display.width", 200)
    print(both[both["fault"] == "AVERAGE"].sort_values("AC@1", ascending=False).round(3).to_string(index=False))
    print(both[both["data_source"] == "this work"].round(3).to_string(index=False))


if __name__ == "__main__":
    main()

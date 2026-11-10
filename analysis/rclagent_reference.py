"""Reference numbers from the RCLAgent paper, next to our results on the same RCAEval subset.

RCLAgent (Zhang et al., "Towards In-Depth Root Cause Localization for Microservices with Multi-Agent
Recursion-of-Thought", arXiv:2605.14866v1, Table I) is evaluated on RCAEval's RE2-OB only (it needs traces, metrics
and logs together), with Recall@k (= RCAEval's AC@k) and MRR (rank beyond 10 counts as 0). Its RCAEval columns are
transcribed below as published (percent). They come from the paper's own case set and protocol, with Claude-3.5-Sonnet
or Qwen-3.6-Plus; they are not re-run here (user decision, WORKLOG 2026-10-28), so the comparison is indicative only.
The earlier version (arXiv:2508.20370v1) used only the AIOps 2022 dataset and has no RCAEval numbers.

Reported results only (user decision 2026-10-29): nothing is re-run. Theirs is the published table (all 90 RE2-OB cases
per the RCLAgent-V2 README); ours is test_r1 waves 1-2 (wave_<tag>_cases.csv), in three views:
  home    RE2-OB, DeepRCA's tuning app (its dev cases were RE2-OB / RE3-OB): an upper bound for DeepRCA
  unseen  RE2-SS and RE2-TT, same data types and fault types as RE2-OB on apps never used in development: conservative
  lift    each system's gain over BARO from RCAEval on its own case set (theirs: paper rows; ours: our Phase 6 run),
          which offsets part of the difference in case difficulty
Same metrics (Recall@k, MRR as defined in the paper). Remaining differences, stated not removed: the model (theirs
Claude-3.5-Sonnet, ours Gemini 3.7 Flash) and their per-fault scoring, which takes the best rank over all error traces
of a case (lenient to RCLAgent; we give one answer per case).

Writes results/rclagent_paper_re2ob.csv, results/rclagent_compare_<tag>.csv, results/rclagent_lift_<tag>.csv.

Our side is scored with rca.scoring.hit_at at service level; MRR uses the paper's definition (1/rank within the top 10,
else 0). R1 gets an exact 95% interval and an exact one-sided binomial test against each published RCLAgent R1.

Writes results/rclagent_paper_re2ob.csv (the paper's table, long form) and results/rclagent_compare_<tag>.csv.
Usage: python analysis/rclagent_reference.py --tag w12_r1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scipy.stats import binomtest  # noqa: E402

from rca.adapter.layout import case_id_for, list_raw_cases  # noqa: E402
from rca.paths import RESULTS_DIR, RUNS_DIR  # noqa: E402
from rca.scoring import hit_at  # noqa: E402

SOURCE = "arXiv:2605.14866v1, Table I, RCAEval (RE2-OB) columns"
# method: R1, R3, R5, R10, MRR (percent, as printed)
PAPER = {
    ("non-LLM", "CRISP"): [14.31, 25.99, 39.13, 47.65, 24.83],
    ("non-LLM", "TraceContrast"): [39.45, 45.33, 56.72, 60.08, 45.79],
    ("non-LLM", "TraceRCA"): [23.34, 45.51, 57.39, 61.38, 38.17],
    ("non-LLM", "MicroRank"): [16.23, 29.39, 32.58, 39.13, 24.73],
    ("non-LLM", "RUN"): [12.34, 25.76, 37.64, 45.95, 23.43],
    ("non-LLM", "MicroScope"): [13.38, 28.79, 40.05, 53.34, 26.16],
    ("non-LLM", "CausalRCA"): [23.39, 44.32, 58.67, 66.15, 36.18],
    ("non-LLM", "Eadro"): [19.13, 43.95, 63.02, 69.37, 37.31],
    ("non-LLM", "Nezha"): [0.00, 0.00, 0.00, 1.10, 0.56],
    ("non-LLM", "BARO"): [18.89, 92.22, 100.00, 100.00, 55.11],
    ("LLM", "CoT"): [13.67, 20.18, 23.16, 28.81, 18.34],
    ("LLM", "RCAgent"): [25.32, 31.09, 39.19, 45.83, 31.28],
    ("LLM", "mABC"): [39.98, 42.13, 44.95, 47.87, 41.76],
    ("LLM", "GALA"): [45.59, 66.83, 75.32, 78.94, 58.93],
    ("LLM", "RCLAgent (Claude-3.5-Sonnet)"): [52.31, 63.15, 79.39, 85.96, 62.97],
    ("LLM", "RCLAgent (Qwen-3.6-Plus)"): [56.67, 80.00, 86.67, 100.00, 71.03],
}
KEYS = ["R1", "R3", "R5", "R10", "MRR"]


def mrr(ranked: list[str], gt: str) -> float:
    for i in range(min(10, len(ranked))):
        if hit_at(ranked[: i + 1], gt, i + 1):
            return 1 / (i + 1)
    return 0.0


def score(name: str, ranked: pd.Series, gt: pd.Series) -> dict:
    r = {"source": "this work", "paradigm": "this work", "method": name, "n_cases": len(gt)}
    for k in (1, 3, 5, 10):
        r[f"R{k}"] = 100 * sum(hit_at(x, g, k) for x, g in zip(ranked, gt)) / len(gt)
    r["MRR"] = 100 * sum(mrr(x, g) for x, g in zip(ranked, gt)) / len(gt)
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    paper = pd.DataFrame([{"source": SOURCE, "paradigm": p, "method": m, "n_cases": None, **dict(zip(KEYS, v))}
                          for (p, m), v in PAPER.items()])
    paper.to_csv(RESULTS_DIR / "rclagent_paper_re2ob.csv", index=False)
    # Already-reported results only (test_r1, waves 1-2); nothing is re-run (user decision 2026-10-29). Three views:
    #   home    RE2-OB: the app DeepRCA was tuned on (dev cases were RE2-OB / RE3-OB), so an upper bound
    #   unseen  RE2-SS + RE2-TT: same data types and fault types as RE2-OB, apps never used in development (conservative)
    #   each unseen app separately
    cases = pd.read_csv(RESULTS_DIR / f"wave_{args.tag}_cases.csv")
    cases["ranked_v3"] = cases["ranked_v3"].map(json.loads)
    ctrl = pd.read_csv(RESULTS_DIR / "control.csv").set_index("case_id")
    sets = {"home: RE2-OB (tuning app, upper bound)": ["RE2-OB"],
            "unseen: RE2-SS + RE2-TT (never tuned on)": ["RE2-SS", "RE2-TT"],
            "unseen: RE2-SS": ["RE2-SS"], "unseen: RE2-TT": ["RE2-TT"]}
    raw = {}
    for ds in ("RE2-OB", "RE2-SS", "RE2-TT"):
        for cd in list_raw_cases(ds)[0]:
            raw[case_id_for(ds, cd)] = cd
    ours = []
    for set_name, dss in sets.items():
        g = cases[cases["dataset"].isin(dss)].reset_index(drop=True)
        for name, ranked in (("DeepRCA (V3, Gemini 3.7 Flash)", g["ranked_v3"]),
                             ("Control (z-score, BARO-style)", g["case_id"].map(lambda c: json.loads(ctrl.loc[c, "ranked_top10"])))):
            ours.append({**score(name, ranked, g["gt_service"]), "case_set": set_name})
        # the paper's own baselines, run by us with RCAEval unmodified on the same cases (Phase 6)
        for m, label in (("baro", "BARO"), ("tracerca", "TraceRCA"), ("microrank", "MicroRank")):
            files = [RUNS_DIR / "rcaeval" / "w12" / m / ds.lower() / "output" / "results" / f"{raw[c].parent.name}_{raw[c].name}.json"
                     for c, ds in zip(g["case_id"], g["dataset"])]
            if not all(f.exists() for f in files):
                print(f"skip {label} on {set_name}: {sum(not f.exists() for f in files)} cases without output")
                continue
            ranked = pd.Series([[str(x) for x in (json.loads(f.read_text()).get("0") or [])] for f in files])
            ours.append({**score(f"{label} (RCAEval, run by us)", ranked, g["gt_service"]), "case_set": set_name})
    ours = pd.DataFrame(ours)
    # R1 with an exact 95% interval, and an exact one-sided binomial test against each RCLAgent R1 as a fixed reference
    hits = (ours["R1"] * ours["n_cases"] / 100).round().astype(int)
    ci = [binomtest(h, n).proportion_ci(0.95) for h, n in zip(hits, ours["n_cases"])]
    ours["R1_ci_low"], ours["R1_ci_high"] = [100 * c.low for c in ci], [100 * c.high for c in ci]
    for label, ref in (("claude", 52.31), ("qwen", 56.67)):
        ours[f"p_above_rclagent_{label}"] = [binomtest(h, n, ref / 100, alternative="greater").pvalue
                                             for h, n in zip(hits, ours["n_cases"])]
    out = pd.concat([paper.assign(case_set="paper: RE2-OB (90 per their README)"), ours], ignore_index=True)
    out.to_csv(RESULTS_DIR / f"rclagent_compare_{args.tag}.csv", index=False)

    # Gain over a shared baseline (BARO from RCAEval): each system minus BARO on its own case set, per metric.
    # RCLAgent: its paper's RCLAgent (Claude) row minus its paper's BARO row. DeepRCA: our V3 minus our RCAEval BARO run.
    lift = []
    pb = paper.set_index("method")
    lift.append({"system": "RCLAgent (Claude-3.5-Sonnet)", "case_set": "paper: RE2-OB",
                 **{k: pb.loc["RCLAgent (Claude-3.5-Sonnet)", k] - pb.loc["BARO", k] for k in KEYS}})
    for set_name in sets:
        o = ours[ours["case_set"] == set_name].set_index("method")
        if "BARO (RCAEval, run by us)" in o.index:
            lift.append({"system": "DeepRCA (V3, Gemini 3.7 Flash)", "case_set": set_name,
                         **{k: o.loc["DeepRCA (V3, Gemini 3.7 Flash)", k] - o.loc["BARO (RCAEval, run by us)", k] for k in KEYS}})
    lift = pd.DataFrame(lift)
    lift.to_csv(RESULTS_DIR / f"rclagent_lift_{args.tag}.csv", index=False)
    pd.set_option("display.width", 220)
    print(out[out["paradigm"].isin(["this work"]) | out["method"].str.startswith(("RCLAgent", "BARO"))]
          .drop(columns=["source", "paradigm"]).round(1).to_string(index=False))
    print("\ngain over BARO (points)")
    print(lift.round(1).to_string(index=False))


if __name__ == "__main__":
    main()

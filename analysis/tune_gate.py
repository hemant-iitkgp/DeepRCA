"""Tune the gate thresholds on the dev split only (SPEC 7.8).

Grid over (max anomalous services, min z margin). Objective: maximise top-1 accuracy of the gated
ranking (V4) on symptom-aligned dev cases, subject to not lowering accuracy on symptom-misleading dev
cases compared with the ungated ranking (V3). Ties: the stricter gate (fewer cases gated).
Reads runs/<run_id>/results.jsonl (one or more dev runs; one row per case and run).
Writes results/gate_tuning_dev.csv (all grid points) and prints the chosen thresholds.

Usage: python analysis/tune_gate.py --runs dev_r1 [dev_r2 ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.guardrails.gate import apply_gate  # noqa: E402
from rca.paths import RESULTS_DIR, RUNS_DIR, SPLITS_CSV  # noqa: E402
from rca.scoring import gt_service_key  # noqa: E402
from rca.truth import load_truth  # noqa: E402


def load_runs(run_ids: list[str]) -> pd.DataFrame:
    rows = []
    for rid in run_ids:
        for line in open(RUNS_DIR / rid / "results.jsonl"):
            r = json.loads(line)
            if "ranked_v3" in r:
                rows.append(r)
    df = pd.DataFrame(rows).drop_duplicates(["run_id", "case_id"], keep="last")
    dev = set(pd.read_csv(SPLITS_CSV).query("split == 'dev'")["case_id"])
    bad = set(df["case_id"]) - dev
    if bad:
        raise SystemExit(f"refusing to tune on non-dev cases: {sorted(bad)[:5]}")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    args = ap.parse_args()
    df = load_runs(args.runs)
    df["gt"] = [gt_service_key(load_truth(d, c)["gt_service"]) for d, c in zip(df["dataset"], df["case_id"])]
    df["aligned"] = [str(t).split("_")[0] == g for t, g in zip(df["control_top1"], df["gt"])]
    df["critic_pass"] = df["critic_verdict"] == "pass"
    v3_hit = (df["ranked_v3"].map(lambda r: r[0] if r else None) == df["gt"])
    base_mis = v3_hit[~df["aligned"]].mean() if (~df["aligned"]).any() else np.nan
    base_al = v3_hit[df["aligned"]].mean() if df["aligned"].any() else np.nan

    anoms = sorted(set(df["control_n_anomalous"].astype(int)))
    margins = sorted(set(np.round(np.quantile(df["control_z_margin"].replace(np.inf, 1e9), np.linspace(0, 0.95, 20)), 2)))
    grid = []
    for ma in anoms:
        for mm in margins:
            hits, gated = [], 0
            for r in df.itertuples():
                ctrl = {"ranked": [r.control_top1], "n_anomalous": r.control_n_anomalous, "z_margin": r.control_z_margin}
                v4, path = apply_gate(r.ranked_v3, ctrl, set(r.top1_positive_evidence), r.critic_pass, ma, mm)
                gated += path.startswith("gate_held")
                hits.append(v4[0] == r.gt)
            hits = pd.Series(hits, index=df.index)
            grid.append({"max_anomalous_services": ma, "min_z_margin": mm, "n_gated": gated,
                         "acc_aligned_v4": hits[df["aligned"]].mean(), "acc_misleading_v4": hits[~df["aligned"]].mean(),
                         "acc_all_v4": hits.mean(), "acc_aligned_v3": base_al, "acc_misleading_v3": base_mis,
                         "acc_all_v3": v3_hit.mean()})
    g = pd.DataFrame(grid)
    g["feasible"] = g["acc_misleading_v4"].fillna(0) >= g["acc_misleading_v3"].fillna(0) - 1e-9
    g = g.sort_values(["feasible", "acc_aligned_v4", "n_gated"], ascending=[False, False, True])
    g.to_csv(RESULTS_DIR / "gate_tuning_dev.csv", index=False)
    best = g.iloc[0]
    print(g.head(10).to_string())
    print("chosen:", {"max_anomalous_services": int(best["max_anomalous_services"]),
                      "min_z_margin": float(best["min_z_margin"])})


if __name__ == "__main__":
    main()

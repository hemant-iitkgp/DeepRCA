"""Paired comparison of the onset-detection run with the given-fault-time run on the same cases (SPEC 9.1).

Reads runs/<onset run> and runs/<provided run> per-case results (via part1_tables.load_runs) and results/control.csv.
For each dataset and overall: AC@1 of both runs and of the control, fixed / broken counts of detected vs provided,
and the exact McNemar p. Writes results/part1_onset_paired.csv.

Usage: python analysis/onset_paired.py --onset test_detect --provided test_r1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from part1_tables import load_runs  # noqa: E402
from rca.paths import RESULTS_DIR  # noqa: E402
from rca.scoring import hit_at  # noqa: E402


def hits(df: pd.DataFrame) -> pd.Series:
    out = {}
    for c, r, gt in zip(df["case_id"], df["ranked_v3"], df["gt_service"]):
        out[c] = hit_at(r if isinstance(r, list) else [], gt, 1)
    return pd.Series(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onset", required=True)
    ap.add_argument("--provided", required=True)
    args = ap.parse_args()
    on = load_runs([args.onset])
    pr = load_runs([args.provided])
    pr = pr[pr["case_id"].isin(set(on["case_id"]))]
    ds = on.set_index("case_id")["dataset"]
    h_on, h_pr = hits(on), hits(pr)
    ctl = pd.read_csv(RESULTS_DIR / "control.csv")
    ctl = ctl.drop_duplicates("case_id").set_index("case_id")
    ctl_hit = ctl["hit1"]
    rows = []
    for key, ids in [("ALL", list(ds.index))] + [(d, list(g.index)) for d, g in ds.groupby(ds)]:
        a, b = h_on.reindex(ids).fillna(False), h_pr.reindex(ids).fillna(False)
        fixed, broken = int((a & ~b).sum()), int((~a & b).sum())
        p = binomtest(fixed, fixed + broken, 0.5).pvalue if fixed + broken else 1.0
        row = {"dataset": key, "n_cases": len(ids), "detected_AC@1": a.mean(), "provided_AC@1": b.mean(),
               "detected_fixed": fixed, "detected_broken": broken, "mcnemar_p": p}
        row["control_AC@1"] = ctl_hit.reindex(ids).astype(float).mean()
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS_DIR / "part1_onset_paired.csv", index=False)
    print(out.to_string())


if __name__ == "__main__":
    main()

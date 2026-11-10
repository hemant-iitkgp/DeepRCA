"""Holm correction across the paired tests behind the Part 2 claims (SPEC 8, multiple comparisons).

The family is every exact McNemar test that a claim in the verdict table rests on:
  overall          V3 vs control, all 339 test cases (results/wave_w12_r1_cases.csv)
  primary          V3 vs control on symptom-misleading and on symptom-aligned cases
  H5 transfer      V3 vs control on the unseen-application cases (Sock Shop and Train Ticket, 245)
  H6 baselines     V3 vs each RCAEval baseline on the cases it answered (results/p2_unseen_baselines.csv, view answered)
Raw p is recomputed here for the first four from the case table, and read from the CSV for the baselines.
Holm step-down: sort raw p ascending, adjusted p_(i) = max over j <= i of min(1, (m - j + 1) p_(j)).

Writes results/p2_holm.csv.
Usage: python analysis/p2_holm.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from p2_common import save
from rca.paths import RESULTS_DIR

UNSEEN = {"SS", "TT"}


def mcnemar(fixed: int, broken: int) -> float:
    return binomtest(fixed, fixed + broken, 0.5).pvalue if fixed + broken else np.nan


def paired(g: pd.DataFrame) -> tuple[int, int]:
    v3, ctl = g["v3_hit1"].astype(bool), g["control_hit1"].astype(bool)
    return int((v3 & ~ctl).sum()), int((~v3 & ctl).sum())


def main() -> None:
    c = pd.read_csv(RESULTS_DIR / "wave_w12_r1_cases.csv")
    tests = []
    for name, claim, g in [("V3 vs control, all cases", "overall", c),
                           ("V3 vs control, misleading cases", "primary", c[~c["symptom_aligned"].astype(bool)]),
                           ("V3 vs control, aligned cases", "primary", c[c["symptom_aligned"].astype(bool)]),
                           ("V3 vs control, unseen applications", "H5", c[c["system"].isin(UNSEEN)])]:
        f, b = paired(g)
        tests.append({"test": name, "claim": claim, "n": len(g), "fixed": f, "broken": b, "p_raw": mcnemar(f, b)})
    bl = pd.read_csv(RESULTS_DIR / "p2_unseen_baselines.csv")
    bl = bl[(bl["view"] == "answered") & bl["mcnemar_p"].notna()]
    for r in bl.itertuples():
        tests.append({"test": f"V3 vs {r.method}", "claim": "H6", "n": int(r.n), "fixed": int(r.deeprca_fixed),
                      "broken": int(r.deeprca_broken), "p_raw": float(r.mcnemar_p)})
    t = pd.DataFrame(tests).sort_values("p_raw").reset_index(drop=True)
    m = len(t)
    adj = np.minimum(1.0, (m - np.arange(m)) * t["p_raw"].to_numpy())
    t["p_holm"] = np.maximum.accumulate(adj)
    t["significant_holm_0.05"] = t["p_holm"] < 0.05
    t["m"] = m
    save(t, "p2_holm.csv")
    pd.set_option("display.width", 200)
    print(t.to_string(index=False))


if __name__ == "__main__":
    main()

"""D2: calibration of the confidence score per dataset (SPEC 10, theme D)

Per dataset and overall: mean confidence, actual AC@1, the gap between them, Brier score (mean squared difference
between confidence and the 0/1 outcome) and AUROC (chance a right answer gets a higher confidence than a wrong one).

Writes results/p2_d2_calibration.csv.
Usage: python analysis/p2_d2_calibration.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from p2_common import load_cases, save


def auroc(s: np.ndarray, y: np.ndarray) -> float:
    pos, neg = s[y], s[~y]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    diff = pos[:, None] - neg[None, :]
    return float(((diff > 0).sum() + 0.5 * (diff == 0).sum()) / diff.size)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    rows = []
    for key, g in [("ALL", d)] + list(d.groupby("dataset")) + list(d.groupby("system")):
        c, y = g["confidence"].to_numpy(float), g["v3_hit1"].to_numpy(bool)
        rows.append({"group": key, "n": len(g), "mean_confidence": c.mean(), "AC@1": y.mean(), "gap": c.mean() - y.mean(),
                     "brier": float(((c - y) ** 2).mean()), "auroc": auroc(c, y)})
    out = pd.DataFrame(rows)
    save(out, "p2_d2_calibration.csv")
    pd.set_option("display.width", 200)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

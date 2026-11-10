"""Fit the confidence model on the dev split only (SPEC 7.7).

Logistic regression of "V4 top-1 correct" on the code-computed features in each result's
`confidence_features`. Writes config/confidence.json (coefficients, source) and
results/confidence_fit_dev.csv (coefficients and dev Brier score).

Usage: python analysis/fit_confidence.py --runs dev_r1 [dev_r2 ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analysis.tune_gate import load_runs  # noqa: E402
from rca.guardrails.confidence import FEATURES  # noqa: E402
from rca.paths import CONFIG_DIR, RESULTS_DIR  # noqa: E402
from rca.scoring import gt_service_key  # noqa: E402
from rca.truth import load_truth  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    args = ap.parse_args()
    df = load_runs(args.runs)
    gt = [gt_service_key(load_truth(d, c)["gt_service"]) for d, c in zip(df["dataset"], df["case_id"])]
    y = [int(bool(r) and r[0] == g) for r, g in zip(df["ranked_v4"], gt)]
    X = pd.DataFrame([f for f in df["confidence_features"]])[FEATURES].astype(float)
    if len(set(y)) < 2:
        raise SystemExit("need both correct and wrong dev cases to fit")
    m = LogisticRegression(C=1.0, max_iter=1000).fit(X, y)
    coef = {"intercept": float(m.intercept_[0]), **{k: float(v) for k, v in zip(FEATURES, m.coef_[0])}}
    p = m.predict_proba(X)[:, 1]
    brier = float(((p - pd.Series(y)) ** 2).mean())
    (CONFIG_DIR / "confidence.json").write_text(json.dumps({"coef": coef, "source": f"dev-fit on {args.runs}",
                                                            "n": len(y), "dev_brier": brier}, indent=1))
    pd.DataFrame([{"term": k, "coef": v} for k, v in coef.items()] + [{"term": "dev_brier", "coef": brier},
                                                                       {"term": "n", "coef": len(y)}]).to_csv(
        RESULTS_DIR / "confidence_fit_dev.csv", index=False)
    print(coef, "brier", brier)


if __name__ == "__main__":
    main()

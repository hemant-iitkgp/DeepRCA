"""Fixed case samples for the Part 2 Phase 7 runs (Option A, user-approved 2026-10-28). Run once; seeded.

From the 339 test cases of waves 1-2 (results/wave_w12_r1_cases.csv):
  data/p2_sample.csv   100 cases, per-dataset quota proportional to the 339 (at least 2 each); within a dataset,
                       misleading cases first up to half the quota, then aligned (so both strata have power)
  data/p2_a2_cases.csv 20 sample cases where V3 was right at #1 (spread over datasets), for planted false leads
  data/p2_c3_cases.csv 30 sample cases with traces, for the hidden-names and traces-off probes
and one injection file per (A2 arm, type, case) under data/p2_injections/<arm>_<type>/<case_id>.json:
  plausible arm   the most anomalous service (control ranking) that is not the true cause
  implausible arm the least anomalous service (last in the control ranking)
  types           fake_flagged_span (a fake suspect on that service), wrong_candidate_rank (it is placed first
                  in both statistical rankings)
Choosing the planted service uses the answer; that is experiment design, done here in analysis code. The system
under test never sees it.

Usage: python analysis/p2_sample.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import DATA_DIR, RESULTS_DIR  # noqa: E402

SEED = 20261028


def main() -> None:
    out = DATA_DIR / "p2_sample.csv"
    if out.exists():
        print(f"{out} exists; samples are fixed once and never redrawn")
        return
    rng = np.random.default_rng(SEED)
    d = pd.read_csv(RESULTS_DIR / "wave_w12_r1_cases.csv")
    n = len(d)
    quota = (d.groupby("dataset").size() * 100 / n).round().astype(int).clip(lower=2)
    while quota.sum() > 100:
        quota[quota.idxmax()] -= 1
    while quota.sum() < 100:
        quota[quota.idxmax()] += 1
    picks = []
    for ds, q in quota.items():
        g = d[d["dataset"] == ds].copy()
        g["r"] = rng.random(len(g))
        mis = g[~g["symptom_aligned"]].sort_values("r")
        ali = g[g["symptom_aligned"]].sort_values("r")
        take = mis.head(q // 2)
        take = pd.concat([take, ali.head(q - len(take))])
        if len(take) < q:
            take = pd.concat([take, mis.iloc[len(take[~take["symptom_aligned"]]):].head(q - len(take))])
        picks.append(take)
    s = pd.concat(picks)[["case_id", "dataset", "system", "symptom_aligned", "v3_hit1"]].sort_values(["dataset", "case_id"])
    s.to_csv(out, index=False)

    right = s[s["v3_hit1"]].copy()
    right["r"] = rng.random(len(right))
    a2 = right.sort_values("r").groupby("dataset").head(3).sort_values("r").head(20).drop(columns="r")
    a2.to_csv(DATA_DIR / "p2_a2_cases.csv", index=False)

    from rca.control.zscore import control_rank
    from rca.tools.data import CaseData

    trace_ds = {"RE2-OB", "RE2-TT", "RE3-OB", "RE3-TT"}
    c3 = s[s["dataset"].isin(trace_ds)].copy()
    c3["r"] = rng.random(len(c3))
    c3.sort_values("r").head(30).drop(columns="r").sort_values(["dataset", "case_id"]).to_csv(DATA_DIR / "p2_c3_cases.csv", index=False)

    truth = d.set_index("case_id")["gt_service"]
    root = DATA_DIR / "p2_injections"
    for c, ds in zip(a2["case_id"], a2["dataset"]):
        ranked = control_rank(CaseData(ds, c))["ranked"]  # every service, most anomalous first
        gt = truth[c]
        others = [x for x in ranked if x != gt]
        arms = {"plausible": others[0], "implausible": others[-1]}
        for arm, svc in arms.items():
            for typ in ("fake_flagged_span", "wrong_candidate_rank"):
                p = root / f"{arm}_{typ}" / f"{c}.json"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({"type": typ, "service": svc, "arm": arm}))
    print(s.groupby(["dataset", "symptom_aligned"]).size().unstack(fill_value=0))
    print(f"A2 cases: {len(a2)}; C3 cases: {min(30, len(c3))}")


if __name__ == "__main__":
    main()

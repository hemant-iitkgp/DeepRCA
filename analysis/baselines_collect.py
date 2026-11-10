"""Collect and score the RCAEval baselines run on our test cases (Part 2, Phase 6).

Reads runs/rcaeval/<tag>/<method>/<dataset>/output/results/<fault folder>_<rep>.json (written by RCAEval's main.py
or baselines/run_trace_methods.py), maps each file to our opaque case ID, and scores it with RCAEval's Evaluator
(rca.scoring), the same way as our own system. A case a method was run on but failed (`_failed.json`) or never
produced counts as a miss (empty ranking), and is listed.

Writes:
  results/baselines.csv              method, dataset, case_id, run, status, ranked (JSON, top 20)
  results/baselines_<tag>_summary.csv  per method x dataset (and ALL over the datasets the method ran on):
                                     n, AC@1, AC@3, AC@5, Avg@5, failures, and our V3 and control on the same cases,
                                     with fixed / broken / exact McNemar p of V3 against the method

Usage: python analysis/baselines_collect.py --tag w12 --ours wave_w12_r1
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
from rca.adapter.layout import case_id_for  # noqa: E402
from rca.paths import RAW_DIR, RESULTS_DIR, RUNS_DIR  # noqa: E402
from rca.scoring import hit_at, score_cases  # noqa: E402


def collect(tag: str, wanted: set[str]) -> pd.DataFrame:
    rows = []
    base = RUNS_DIR / "rcaeval" / tag
    for mdir in sorted(p for p in base.iterdir() if p.is_dir()):
        for ddir in sorted(p for p in mdir.iterdir() if p.is_dir()):
            ds = ddir.name.upper()
            res = ddir / "output" / "results"
            if not res.exists():
                continue
            for f in sorted(res.glob("*.json")):
                stem = f.stem
                failed = stem.endswith("_failed")
                if failed:
                    stem = stem[: -len("_failed")]
                folder, rep = stem.rsplit("_", 1)
                cid = case_id_for(ds, RAW_DIR / ds / folder / rep)
                if cid not in wanted:
                    continue
                d = json.loads(f.read_text())
                ranked = [] if failed else [str(x) for x in (d.get("0") or d.get(0) or [])]
                rows.append({"method": mdir.name, "dataset": ds, "case_id": cid, "run": 1,
                             "status": "failed" if failed else "ok", "ranked": ranked})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--ours", required=True, help="prefix of our per-case table, e.g. wave_w12_r1")
    args = ap.parse_args()
    ours = pd.read_csv(RESULTS_DIR / f"{args.ours}_cases.csv")
    ours["ranked_v3"] = ours["ranked_v3"].map(json.loads)
    ctrl = pd.read_csv(RESULTS_DIR / "control.csv").set_index("case_id")
    wanted = set(ours["case_id"])
    bl = collect(args.tag, wanted)
    # cases a method should have covered but produced no file for count as misses ("missing")
    from rca.adapter.layout import list_raw_cases

    raw_dir = {}
    for ds in ours["dataset"].unique():
        for cd in list_raw_cases(ds)[0]:
            raw_dir[case_id_for(ds, cd)] = cd
    trace_methods = {"tracerca", "microrank", "pdiagnose"}
    add = []
    for (method, ds), g in bl.groupby(["method", "dataset"]):
        exp = ours.loc[ours["dataset"] == ds, "case_id"]
        if method in trace_methods:
            exp = [c for c in exp if (raw_dir[c] / "traces.csv").exists()]
        for c in sorted(set(exp) - set(g["case_id"])):
            add.append({"method": method, "dataset": ds, "case_id": c, "run": 1, "status": "missing", "ranked": []})
    if add:
        bl = pd.concat([bl, pd.DataFrame(add)], ignore_index=True)

    out = bl.copy()
    out["ranked"] = out["ranked"].map(lambda r: json.dumps(r[:20]))
    out.to_csv(RESULTS_DIR / "baselines.csv", index=False)

    o = ours.set_index("case_id")
    rows = []
    for method, g in bl.groupby("method"):
        for key, gg in [("ALL", g)] + list(g.groupby("dataset")):
            gg = gg.copy()
            gt = o.loc[gg["case_id"], "gt_service"].values
            sm = score_cases([{"ranked": r, "gt_service": s, "fault": "", "dataset": d}
                              for r, s, d in zip(gg["ranked"], gt, gg["dataset"])], "service")
            hb = np.array([hit_at(r, s, 1) for r, s in zip(gg["ranked"], gt)], float)
            h3 = np.array([hit_at(r, s, 1) for r, s in zip(o.loc[gg["case_id"], "ranked_v3"], gt)], float)
            hc = np.array([hit_at(json.loads(ctrl.loc[c, "ranked_top10"]), s, 1) for c, s in zip(gg["case_id"], gt)], float)
            fixed, broken = int(((h3 == 1) & (hb == 0)).sum()), int(((h3 == 0) & (hb == 1)).sum())
            rows.append({"method": method, "dataset": key, "n_cases": len(gg), "failures": int((gg["status"] != "ok").sum()),
                         "AC@1": sm.get("AC@1"), "AC@3": sm.get("AC@3"), "AC@5": sm.get("AC@5"), "Avg@5": sm.get("Avg@5"),
                         "ours_v3_AC@1": h3.mean(), "control_AC@1": hc.mean(),
                         "v3_fixed_vs_method": fixed, "v3_broken_vs_method": broken,
                         "mcnemar_p": binomtest(fixed, fixed + broken, 0.5).pvalue if fixed + broken else np.nan})
    summ = pd.DataFrame(rows)
    summ.to_csv(RESULTS_DIR / f"baselines_{args.tag}_summary.csv", index=False)
    pd.set_option("display.width", 220)
    print(summ.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

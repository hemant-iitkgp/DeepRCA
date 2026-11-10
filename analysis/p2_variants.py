"""Phase 7 variant runs against the frozen system's own run 1 on the same cases (C1 ladder, C3.2, D1, E3, E5).

For every finished case of each variant run (runs/<run_id>/<case>/result.json), the variant's answer is compared with
V3 from test_r1 on the same case:
  AC@1, AC@3, Avg@5 of both (RCAEval Evaluator), fixed / broken (variant right only / V3 right only),
  exact McNemar p, top-1 agreement (same #1 service), mean cost and minutes per case, report status counts.
Anonymised runs (p2_anon) answer with aliases svc_00..; they are mapped back with the same rename the runner uses
(sorted service names -> svc_<i>).

Writes results/p2_variants_cases.csv and results/p2_variants_summary.csv.
Usage: python analysis/p2_variants.py [--runs p2_mini p2_rerun ...]
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from p2_common import load_cases, save
from rca.paths import RUNS_DIR
from rca.scoring import hit_at, score_cases
from rca.tools.data import CaseData

RUNS = ["p2_rerun", "p2_anon", "p2_mini", "p2_nocritic", "p2_noguard", "p2_single", "p2_codeloop", "p2_notraces"]


def unalias(dataset: str, case_id: str, ranked: list[str]) -> list[str]:
    back = {f"svc_{i:02d}": s for i, s in enumerate(sorted(CaseData(dataset, case_id).services))}
    return [back.get(x, x) for x in ranked]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=RUNS)
    args = ap.parse_args()
    base = load_cases("w12_r1").set_index("case_id")
    rows = []
    for run in args.runs:
        d = RUNS_DIR / run
        if not d.exists():
            continue
        for p in sorted(d.glob("*/result.json")):
            r = json.loads(p.read_text())
            c = r["case_id"]
            if c not in base.index:
                continue
            b = base.loc[c]
            ranked = r.get("ranked_v3") or []
            if run == "p2_anon":
                ranked = unalias(r["dataset"], c, ranked)
            rows.append({"run": run, "case_id": c, "dataset": r["dataset"], "symptom_aligned": bool(b["symptom_aligned"]),
                         "gt_service": b["gt_service"], "ranked": ranked, "v3_ranked": b["ranked_v3"],
                         "status": r.get("status"), "report_status": r.get("report_status"),
                         "cost_usd": r.get("cost_usd"), "latency_s": r.get("latency_s")})
    c = pd.DataFrame(rows)
    if c.empty:
        print("no finished variant cases yet")
        return
    c["hit1"] = [hit_at(x, g, 1) for x, g in zip(c["ranked"], c["gt_service"])]
    c["v3_hit1"] = [hit_at(x, g, 1) for x, g in zip(c["v3_ranked"], c["gt_service"])]
    c["same_top1"] = [bool(x) and bool(y) and x[0] == y[0] for x, y in zip(c["ranked"], c["v3_ranked"])]
    out = c.drop(columns=["ranked", "v3_ranked"]).copy()
    out["top1"] = c["ranked"].map(lambda x: x[0] if x else None)
    out["v3_top1"] = c["v3_ranked"].map(lambda x: x[0] if x else None)
    save(out, "p2_variants_cases.csv")
    summ = []
    for (run, grp), g in [((r, "ALL"), g) for r, g in c.groupby("run")] + \
            [((r, "aligned" if a else "misleading"), g) for (r, a), g in c.groupby(["run", "symptom_aligned"])]:
        rows_v = [{"ranked": x, "gt_service": s, "fault": "", "dataset": d} for x, s, d in zip(g["ranked"], g["gt_service"], g["dataset"])]
        rows_b = [{"ranked": x, "gt_service": s, "fault": "", "dataset": d} for x, s, d in zip(g["v3_ranked"], g["gt_service"], g["dataset"])]
        sv, sb = score_cases(rows_v), score_cases(rows_b)
        fixed = int((g["hit1"] & ~g["v3_hit1"]).sum())
        broken = int((~g["hit1"] & g["v3_hit1"]).sum())
        summ.append({"run": run, "group": grp, "n": len(g), "AC@1": sv["AC@1"], "AC@3": sv["AC@3"], "Avg@5": sv["Avg@5"],
                     "v3_AC@1": sb["AC@1"], "v3_AC@3": sb["AC@3"], "v3_Avg@5": sb["Avg@5"],
                     "fixed_vs_v3": fixed, "broken_vs_v3": broken,
                     "mcnemar_p": binomtest(fixed, fixed + broken, 0.5).pvalue if fixed + broken else np.nan,
                     "same_top1_as_v3": g["same_top1"].mean(), "cost_usd_mean": g["cost_usd"].mean(),
                     "minutes_mean": g["latency_s"].mean() / 60,
                     "accepted_reports": int((g["report_status"] == "accepted").sum()),
                     "forced_or_none": int((g["report_status"] != "accepted").sum())})
    s = pd.DataFrame(summ)
    save(s, "p2_variants_summary.csv")
    pd.set_option("display.width", 250)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

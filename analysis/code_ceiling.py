"""Code-only ceiling (SPEC Phase 3 / Phase 5 step 5).

For each trace-bearing case of the split: run select_traces and trace_tree (no LLM). Does the true
root-cause service appear among the services that flagged spans point at? Among the top-5 when
flagged spans are ordered by their strongest own-time or edge-gap z?

Usage: python analysis/code_ceiling.py --split dev   -> results/code_ceiling_dev.csv
       python analysis/code_ceiling.py --split test  -> results/code_ceiling_test.csv
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RESULTS_DIR, SPLITS_CSV  # noqa: E402
from rca.scoring import gt_service_key  # noqa: E402
from rca.truth import load_truth  # noqa: E402


def one(args):
    ds, cid = args
    from rca.tools.data import CaseData
    from rca.tools.traces import select_traces, trace_tree

    cd = CaseData(ds, cid)
    if not cd.case["has_traces"]:
        return None
    gt = gt_service_key(load_truth(ds, cid)["gt_service"])
    sel = select_traces(cd)
    flagged = []
    for t in sel:
        flagged += trace_tree(cd, t["trace_id"])["flagged"]
    strength = {}
    for f in flagged:
        z = max(np.nan_to_num(f.get("own_z") or 0), np.nan_to_num(f.get("gap_z") or 0), 50.0 if "error_status" in f["reasons"] else 0)
        for b in f.get("blamed_services") or [f["blamed_service"]]:
            s = gt_service_key(b)
            strength[s] = max(strength.get(s, 0), z)
    order = sorted(strength, key=lambda s: (-strength[s], s))
    entry = {gt_service_key(t["entry_service"]) for t in sel}
    return {"dataset": ds, "case_id": cid, "gt_service": gt, "n_selected_traces": len(sel), "n_flagged_spans": len(flagged),
            "n_flagged_services": len(order), "gt_flagged": gt in strength,
            "gt_rank_by_z": order.index(gt) + 1 if gt in order else None,
            "gt_in_top5": gt in order[:5], "gt_is_entry_service": gt in entry,
            "flagged_services": ";".join(order[:12])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    sp = pd.read_csv(SPLITS_CSV)
    sp = sp[sp["split"] == args.split]
    jobs = [(r.dataset, r.case_id) for r in sp.itertuples()]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = [r for r in ex.map(one, jobs) if r is not None]
    df = pd.DataFrame(rows).sort_values(["dataset", "case_id"])
    summ = []
    for key, g in [("ALL", df)] + list(df.groupby("dataset")):
        summ.append({"dataset": key, "case_id": "SUMMARY", "n_cases": len(g), "gt_flagged": g["gt_flagged"].mean(),
                     "gt_in_top5": g["gt_in_top5"].mean(), "mean_flagged_services": g["n_flagged_services"].mean()})
    out = pd.concat([df, pd.DataFrame(summ)], ignore_index=True)
    name = f"code_ceiling_{args.split}{args.tag}.csv"
    out.to_csv(RESULTS_DIR / name, index=False)
    print(pd.DataFrame(summ).to_string())


if __name__ == "__main__":
    main()

"""Phase 6 gate: a recorded reason for every baseline case without a ranking (SPEC Phase 6, Gate).

Reads results/baselines.csv (status failed or missing) and, for each such case, the method's own error message from
runs/rcaeval/<tag>/<method>/<dataset>/output/results/<folder>_<rep>_failed.json, or the folder skipped by
run_rcaeval.py because RCAEval's main.py cannot parse its name (skipped.json). Errors are grouped per method and
dataset.

Writes results/baselines_gaps.csv (method, dataset, status, n_cases, reason).
Usage: python analysis/baselines_gaps.py [--tag w12]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.adapter.layout import case_id_for, list_raw_cases  # noqa: E402
from rca.paths import RESULTS_DIR, RUNS_DIR  # noqa: E402

SKIP_REASON = ("RCAEval main.py cannot parse the case folder name (variant suffix, e.g. '<service>_f3_1'), "
               "so main.py never sees the case")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12")
    args = ap.parse_args()
    bl = pd.read_csv(RESULTS_DIR / "baselines.csv")
    gaps = bl[bl["status"] != "ok"]
    folder = {}
    for ds in gaps["dataset"].unique():
        for p in list_raw_cases(ds)[0]:
            folder[(ds, case_id_for(ds, p))] = p
    rows = []
    for (m, ds, status), g in gaps.groupby(["method", "dataset", "status"]):
        work = RUNS_DIR / "rcaeval" / args.tag / m / ds.lower()
        skipped = set(json.loads((work / "skipped.json").read_text())) if (work / "skipped.json").exists() else set()
        reasons = Counter()
        for cid in g["case_id"]:
            p = folder.get((ds, cid))
            if p is None:
                reasons["case folder not found"] += 1
            elif status == "missing" and p.parent.name in skipped:
                reasons[SKIP_REASON] += 1
            else:
                f = work / "output" / "results" / f"{p.parent.name}_{p.name}_failed.json"
                err = json.loads(f.read_text()).get("error", "") if f.exists() else "no output and no error file"
                reasons[f"method crash: {err.splitlines()[0][:160]}"] += 1
        for r, n in reasons.most_common():
            rows.append({"method": m, "dataset": ds, "status": status, "n_cases": n, "reason": r})
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS_DIR / "baselines_gaps.csv", index=False)
    pd.set_option("display.width", 250, "display.max_colwidth", 120)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()

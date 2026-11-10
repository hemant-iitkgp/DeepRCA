"""Phase 2: run the z-score control on every case and write results/control.csv.

One row per case: dataset, case_id, split, control ranking (top 10), top-1, its score, number of anomalous
services (z > 2.5), z margin top-1 vs top-2, hit@1/3/5 and the case's ground truth (scorer side only).
Also writes results/control_summary.csv: AC@1/3/5 and Avg@5 per dataset via RCAEval's Evaluator.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RESULTS_DIR, SPLITS_CSV  # noqa: E402
from rca.scoring import hit_at, score_cases  # noqa: E402
from rca.truth import load_truth  # noqa: E402


def one(args):
    ds, cid = args
    from rca.control.zscore import control_rank
    from rca.tools.data import CaseData

    c = control_rank(CaseData(ds, cid))
    t = load_truth(ds, cid)
    r = c["ranked"]
    return {"dataset": ds, "case_id": cid, "control_top1": r[0] if r else None, "control_top1_z": c["top1_z"],
            "n_anomalous": c["n_anomalous"], "z_margin": c["z_margin"], "z_ratio": c["z_ratio"],
            "ranked_top10": json.dumps(r[:10]), "n_services": len(r),
            "gt_service": t["gt_service"], "gt_fault_type": t["gt_fault_type"],
            "hit1": hit_at(r, t["gt_service"], 1), "hit3": hit_at(r, t["gt_service"], 3), "hit5": hit_at(r, t["gt_service"], 5),
            "ranked_full": json.dumps(r)}


def main() -> None:
    sp = pd.read_csv(SPLITS_CSV)
    jobs = [(r.dataset, r.case_id) for r in sp.itertuples()]
    with ProcessPoolExecutor(6) as ex:
        rows = list(ex.map(one, jobs, chunksize=4))
    df = pd.DataFrame(rows).merge(sp[["case_id", "split"]], on="case_id")
    df["symptom_aligned"] = df["hit1"]
    df.drop(columns=["ranked_full"]).to_csv(RESULTS_DIR / "control.csv", index=False)
    summ = []
    for (ds, split), g in [(("ALL", "all"), df)] + list(df.groupby(["dataset", "split"])):
        rows_ = [{"ranked": json.loads(x), "gt_service": s, "fault": f, "dataset": d}
                 for x, s, f, d in zip(g["ranked_full"], g["gt_service"], g["gt_fault_type"], g["dataset"])]
        sc = score_cases(rows_, "service")
        summ.append({"dataset": ds, "split": split, **{k: round(v, 4) if isinstance(v, float) else v for k, v in sc.items()}})
    pd.DataFrame(summ).to_csv(RESULTS_DIR / "control_summary.csv", index=False)
    print(pd.DataFrame(summ).to_string())


if __name__ == "__main__":
    main()

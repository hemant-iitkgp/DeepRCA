"""How well does the agent eliminate the suspects code hands it? (Part 2, Phase 8 follow-up to C5)

Suspects per case are those of p2_c5_ceiling.py (services blamed by code work items, or registered anomalous services).
Two levels, both scored against ground truth (service key match as in rca.scoring):

  decision   a suspect is eliminated when it is not the final #1 (V3). Correct elimination = a non-cause suspect not
             ranked #1; wrong elimination = the true cause on the list but not ranked #1.
  finding    each investigator finding names a service and a verdict. It eliminates that service when it does not
             blame the service itself (not abnormal, blame none, or blame passed to a child or an edge). Correct =
             eliminates a non-cause service; wrong = eliminates the true cause; kept = blames the service itself.

Writes results/p2_elimination_summary.csv.
Usage: python analysis/p2_elimination.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse

import pandas as pd

from p2_common import findings, load_cases, provenance, save
from rca.scoring import gt_service_key


def suspects_of(run_dir) -> set[str]:
    out = set()
    for it in provenance(run_dir).get("work_items", []):
        for s in (it.get("blamed_services") or [it.get("blamed_service")]):
            if isinstance(s, str):
                out.add(s)
        if it.get("kind") == "service" and isinstance(it.get("service"), str):
            out.add(it["service"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    dec, fnd = [], []
    for r in d.itertuples():
        gt = gt_service_key(r.gt_service)
        top = gt_service_key(r.ranked_v3[0]) if r.ranked_v3 else None
        for s in suspects_of(r.run_dir):
            is_cause = gt_service_key(s) == gt
            dec.append({"dataset": r.dataset, "is_cause": is_cause, "eliminated": gt_service_key(s) != top})
        for f in findings(r.run_dir):
            s = f.get("service")
            if not isinstance(s, str):
                continue
            blames_self = bool(f.get("abnormal")) and str(f.get("blame", "none")) == "self"
            fnd.append({"dataset": r.dataset, "is_cause": gt_service_key(s) == gt, "eliminated": not blames_self})
    rows = []
    for level, t in (("decision", pd.DataFrame(dec)), ("finding", pd.DataFrame(fnd))):
        for grp, g in [("ALL", t)] + list(t.groupby("dataset")):
            non, cause = g[~g["is_cause"]], g[g["is_cause"]]
            rows.append({"level": level, "dataset": grp,
                         "non_cause_items": len(non), "non_cause_eliminated": int(non["eliminated"].sum()),
                         "correct_elimination_rate": non["eliminated"].mean() if len(non) else None,
                         "cause_items": len(cause), "cause_eliminated": int(cause["eliminated"].sum()),
                         "wrong_elimination_rate": cause["eliminated"].mean() if len(cause) else None})
    s = pd.DataFrame(rows)
    save(s, "p2_elimination_summary.csv")
    pd.set_option("display.width", 200)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

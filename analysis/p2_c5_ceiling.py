"""C5: code-flagged causes vs the agent's answer (SPEC 10, theme C)

For each case: did code register the true root cause as a suspect (a work item whose blamed services include it, or
an anomalous-service item for it; provenance.json work_items)? Crossed with whether the agent's V3 #1 is right:
  flagged & right    the agent kept a cause code had found
  flagged & wrong    the agent lost a cause code had found
  not flagged & right the agent found a cause code had not flagged
  not flagged & wrong neither

Writes results/p2_c5_cases.csv and results/p2_c5_summary.csv.
Usage: python analysis/p2_c5_ceiling.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse

import pandas as pd

from p2_common import load_cases, provenance, save


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    rows = []
    for r in d.itertuples():
        items = provenance(r.run_dir).get("work_items", [])
        suspects = set()
        for it in items:
            for s in (it.get("blamed_services") or [it.get("blamed_service")]):
                if isinstance(s, str):
                    suspects.add(s)
            if it.get("kind") == "service" and isinstance(it.get("service"), str):
                suspects.add(it["service"])
        rows.append({"case_id": r.case_id, "dataset": r.dataset, "system": r.system, "n_items": len(items),
                     "n_suspects": len(suspects), "flagged": r.gt_service in suspects, "correct": bool(r.v3_hit1),
                     "fault_type": r.gt_fault_type,
                     "suspects_from": "traces" if any(it.get("kind") == "span" for it in items)
                     else ("metrics" if items else "none")})
    c = pd.DataFrame(rows)
    save(c, "p2_c5_cases.csv")
    out = []
    for key, g in [("ALL", c)] + list(c.groupby("dataset")):
        out.append({"group": key, "n": len(g), "code_flagged_true_cause": g["flagged"].mean(),
                    "flagged_and_right": int((g["flagged"] & g["correct"]).sum()),
                    "flagged_and_wrong": int((g["flagged"] & ~g["correct"]).sum()),
                    "not_flagged_and_right": int((~g["flagged"] & g["correct"]).sum()),
                    "not_flagged_and_wrong": int((~g["flagged"] & ~g["correct"]).sum()),
                    "agent_accuracy_when_flagged": g.loc[g["flagged"], "correct"].mean() if g["flagged"].any() else None,
                    "mean_suspects": g["n_suspects"].mean()})
    s = pd.DataFrame(out)
    save(s, "p2_c5_summary.csv")
    # where the suspect list misses the cause: by source of the suspects (trace flags, metric anomalies) and fault type
    by = (c.groupby(["suspects_from", "fault_type"])
          .agg(n=("flagged", "size"), code_flagged_true_cause=("flagged", "mean"), agent_correct=("correct", "mean"))
          .reset_index())
    save(by, "p2_c5_by_fault.csv")
    pd.set_option("display.width", 220)
    print(s.round(3).to_string(index=False))
    print(by.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

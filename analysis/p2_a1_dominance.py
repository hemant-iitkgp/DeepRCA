"""A1: does one component dominate the answer? (SPEC 10, theme A; observational, from provenance)

The running top suspect is recorded after every step (state.note): code tools and investigators/testers move it
through the evidence support score; the main agent moves it when it writes a draft; the critic only when it fails
the draft with an alternative. For every case:
  originator   = component of the first step that made the final answer (V3 #1) the running top
  changers     = components that changed the running top at least once
  draft_vs_evidence = the main agent's draft #1 against the evidence leader just before its first draft
                      (agrees / overrides), with correctness of both

Writes results/p2_a1_cases.csv (one row per case) and results/p2_a1_summary.csv.
Usage: python analysis/p2_a1_dominance.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse

import pandas as pd

from p2_common import load_cases, provenance, save
from rca.scoring import gt_service_key


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    rows = []
    for r in d.itertuples():
        steps = provenance(r.run_dir).get("steps", [])
        final = r.ranked_v3[0] if r.ranked_v3 else None
        orig, changers, leader_before_draft, draft_top = None, set(), None, None
        running = None
        for s in steps:
            tc = s.get("top_changed")
            if s.get("component") == "main_agent" and s.get("event") == "write_draft" and draft_top is None:
                leader_before_draft = running
                draft_top = s.get("running_top")
            if tc:
                changers.add(s["component"])
                if tc.get("to") == final and orig is None:
                    orig = s["component"]
            running = s.get("running_top")
        gt = gt_service_key(r.gt_service)
        ok = lambda x: x is not None and gt_service_key(str(x)) == gt  # noqa: E731
        rows.append({"case_id": r.case_id, "dataset": r.dataset, "symptom_aligned": r.symptom_aligned,
                     "final": final, "correct": bool(r.v3_hit1), "originator": orig or "none_recorded",
                     **{f"changed_by_{c}": c in changers for c in ("code_tool", "investigator", "tester", "main_agent", "critic")},
                     "evidence_leader_before_draft": leader_before_draft, "first_draft_top": draft_top,
                     "draft_overrides_evidence": (leader_before_draft is not None and draft_top is not None
                                                  and leader_before_draft != draft_top),
                     "evidence_leader_correct": ok(leader_before_draft), "first_draft_correct": ok(draft_top)})
    c = pd.DataFrame(rows)
    save(c, "p2_a1_cases.csv")
    summ = []
    n = len(c)
    for comp, g in c.groupby("originator"):
        summ.append({"measure": "originates_final_answer", "group": comp, "n": len(g), "share": len(g) / n,
                     "accuracy": g["correct"].mean()})
    for comp in ("code_tool", "investigator", "tester", "main_agent", "critic"):
        col = f"changed_by_{comp}"
        summ.append({"measure": "changed_running_top", "group": comp, "n": int(c[col].sum()), "share": c[col].mean(),
                     "accuracy": c.loc[c[col], "correct"].mean() if c[col].any() else None})
    has = c[c["evidence_leader_before_draft"].notna() & c["first_draft_top"].notna()]
    for key, g in has.groupby("draft_overrides_evidence"):
        summ.append({"measure": "draft_vs_evidence_leader", "group": "overrides" if key else "agrees", "n": len(g),
                     "share": len(g) / len(has), "accuracy": g["first_draft_correct"].mean(),
                     "evidence_leader_accuracy": g["evidence_leader_correct"].mean(),
                     "fixed_by_override": int((g["first_draft_correct"] & ~g["evidence_leader_correct"]).sum()),
                     "broken_by_override": int((~g["first_draft_correct"] & g["evidence_leader_correct"]).sum())})
    s = pd.DataFrame(summ)
    save(s, "p2_a1_summary.csv")
    pd.set_option("display.width", 200)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

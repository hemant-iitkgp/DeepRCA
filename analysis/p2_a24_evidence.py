"""A2.4: does the evidence ever disconfirm? (SPEC 10, theme A; OmniRCA: 0 of 329 items disconfirming)

Every finding and hypothesis file of the stored runs is classified:
  finding verdict     abnormal & blames a service / abnormal & blame none / not abnormal (clears the suspect)
  hypothesis verdict  supported / refuted / inconclusive
  evidence_against    "substantive" when at least one item states a counter-observation, "checked-none" when every
                      item only says nothing was found (starts with no / none / not / 0 ...), "empty" otherwise
Evidence-for items are counted by type, and items without a type (plain text) are counted separately.

Writes results/p2_a24_items.csv (one row per finding/hypothesis) and results/p2_a24_summary.csv.
Usage: python analysis/p2_a24_evidence.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse
import re

import pandas as pd

from p2_common import findings, hypotheses, load_cases, save
from rca.guardrails.support import ev_items

NONE_RX = re.compile(r"^\s*(no|none|not|nothing|0|zero|did not|didn't|absence|checked)\b", re.I)


def against_kind(items) -> str:
    it = ev_items(items)
    if not it:
        return "empty"
    if all(NONE_RX.search(str(e.get("detail", ""))) for e in it):
        return "checked-none"
    return "substantive"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    rows = []
    for r in d.itertuples():
        for f in findings(r.run_dir):
            blame = str(f.get("blame", "none"))
            verdict = ("clears" if not f.get("abnormal") else "abnormal_blame_none" if blame == "none" else "abnormal_blames")
            ef = ev_items(f.get("evidence_for"))
            rows.append({"case_id": r.case_id, "dataset": r.dataset, "kind": "finding", "verdict": verdict,
                         "against": against_kind(f.get("evidence_against")), "n_for": len(ef),
                         "n_for_untyped": sum(e.get("type") == "other" for e in ef)})
        for h in hypotheses(r.run_dir):
            ef = ev_items(h.get("evidence_for"))
            rows.append({"case_id": r.case_id, "dataset": r.dataset, "kind": "hypothesis", "verdict": h.get("verdict"),
                         "against": against_kind(h.get("evidence_against")), "n_for": len(ef),
                         "n_for_untyped": sum(e.get("type") == "other" for e in ef)})
    it = pd.DataFrame(rows)
    save(it, "p2_a24_items.csv")
    summ = []
    for kind, g in it.groupby("kind"):
        for col in ("verdict", "against"):
            for k, n in g[col].value_counts().items():
                summ.append({"kind": kind, "field": col, "value": k, "n": int(n), "share": n / len(g)})
        summ.append({"kind": kind, "field": "no_evidence_for", "value": "count", "n": int((g["n_for"] == 0).sum()),
                     "share": (g["n_for"] == 0).mean()})
    s = pd.DataFrame(summ)
    save(s, "p2_a24_summary.csv")
    pd.set_option("display.width", 200)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

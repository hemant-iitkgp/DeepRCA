"""A2: does DeepRCA accept planted false leads? (SPEC 10 theme A; OmniRCA: 45% of baseless accusations accepted,
0% after its fix)

Runs p2_a2_<arm>_<type> on data/p2_a2_cases.csv (20 cases DeepRCA answered correctly in test_r1). Per run:
  accepted   the final #1 is the planted service
  recovered  the final #1 is the true cause
  planted_cleared   (fake_flagged_span only) the finding on the planted work item does not blame it
compared with test_r1 on the same cases (all right by construction): broken = recovered there, not here.

Writes results/p2_a2_cases.csv and results/p2_a2_summary.csv.
Usage: python analysis/p2_a2_injection.py
"""
from __future__ import annotations

import json

import pandas as pd

from p2_common import save
from rca.paths import DATA_DIR, RUNS_DIR
from rca.scoring import gt_service_key


def main() -> None:
    cases = pd.read_csv(DATA_DIR / "p2_a2_cases.csv")
    truth = pd.read_csv(DATA_DIR.parent / "results" / "wave_w12_r1_cases.csv").set_index("case_id")["gt_service"]
    rows = []
    for arm in ("plausible", "implausible"):
        for typ in ("fake_flagged_span", "wrong_candidate_rank"):
            run = f"p2_a2_{arm}_{typ}"
            for c in cases["case_id"]:
                p = RUNS_DIR / run / c / "result.json"
                if not p.exists():
                    continue
                r = json.loads(p.read_text())
                planted = json.loads((DATA_DIR / "p2_injections" / f"{arm}_{typ}" / f"{c}.json").read_text())["service"]
                top = (r.get("ranked_v3") or [None])[0]
                cleared = None
                if typ == "fake_flagged_span":
                    f = RUNS_DIR / run / c / "files" / "evidence" / "span_inj0001.json"
                    if f.exists():
                        fd = json.loads(f.read_text())
                        blame = str(fd.get("blame", "none"))
                        blames_planted = blame == "self" or blame.endswith("->" + planted)
                        cleared = not (fd.get("abnormal") and blames_planted)
                rows.append({"run": run, "arm": arm, "type": typ, "case_id": c, "planted": planted, "top1": top,
                             "accepted": top == planted,
                             "recovered": top is not None and gt_service_key(top) == gt_service_key(truth[c]),
                             "planted_cleared": cleared, "report_status": r.get("report_status"),
                             "rejections": r.get("guardrail_rejections")})
    d = pd.DataFrame(rows)
    if d.empty:
        print("no finished A2 cases yet")
        return
    save(d, "p2_a2_cases.csv")
    s = d.groupby(["arm", "type"]).agg(n=("case_id", "size"), accepted=("accepted", "sum"), accepted_share=("accepted", "mean"),
                                       recovered=("recovered", "sum"), recovered_share=("recovered", "mean"),
                                       planted_cleared=("planted_cleared", lambda x: x.dropna().mean() if x.notna().any() else None),
                                       guardrail_rejections=("rejections", "sum")).reset_index()
    tot = d.groupby("arm").agg(n=("case_id", "size"), accepted=("accepted", "sum"), accepted_share=("accepted", "mean"),
                               recovered=("recovered", "sum"), recovered_share=("recovered", "mean")).reset_index()
    tot["type"] = "both"
    s = pd.concat([s, tot], ignore_index=True)
    save(s, "p2_a2_summary.csv")
    pd.set_option("display.width", 200)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

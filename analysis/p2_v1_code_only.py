"""C1 rung V1: a code-only ranking, with no LLM, from what the code tools gave the agent (SPEC 10, theme C).

For every test case of run 1, the work items recorded in provenance.json (the code-flagged suspects the agent started
from) are turned into a ranking without any model call:
  traced cases     services blamed by flagged spans, deepest span first (the "follow the wait down" rule), ties by
                   the larger of the span's own-time and edge-gap scores;
  no-trace cases   anomalous-service items in the code's own order (callee before caller), ties by the number of
                   anomalous metrics;
then every remaining service in the control's order (rca.control.zscore.control_rank), so the list is complete.
Compared with V3 (the agent's answer) and with the control on the same cases: AC@1, AC@3, Avg@5, fixed / broken,
exact McNemar.

Writes results/p2_v1_cases.csv and results/p2_v1_summary.csv.
Usage: python analysis/p2_v1_code_only.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from p2_common import load_cases, provenance, save
from rca.control.zscore import control_rank
from rca.scoring import hit_at, score_cases
from rca.tools.data import CaseData


def code_rank(items: list[dict]) -> list[str]:
    spans = [i for i in items if i.get("kind") == "span"]
    if spans:
        best = {}
        for i in spans:
            z = max(float(i.get("own_z") or 0), float(i.get("gap_z") or 0))
            key = (int(i.get("depth") or 0), z)
            for s in (i.get("blamed_services") or [i.get("blamed_service")]):
                if isinstance(s, str) and (s not in best or key > best[s]):
                    best[s] = key
        return [s for s, _ in sorted(best.items(), key=lambda kv: kv[1], reverse=True)]
    svc = [i for i in items if i.get("kind") == "service" and isinstance(i.get("service"), str)]
    svc.sort(key=lambda i: (int(i.get("order") or 0), -int(i.get("n_anomalous_metrics") or 0)))
    return [i["service"] for i in svc]


def main() -> None:
    d = load_cases("w12_r1")
    rows = []
    for r in d.itertuples():
        ctl = control_rank(CaseData(r.dataset, r.case_id))["ranked"]
        code = code_rank(provenance(r.run_dir).get("work_items", []))
        ranked = code + [s for s in ctl if s not in code]
        rows.append({"case_id": r.case_id, "dataset": r.dataset, "symptom_aligned": bool(r.symptom_aligned),
                     "gt_service": r.gt_service, "n_code_suspects": len(code), "ranked": ranked,
                     "v3_ranked": r.ranked_v3, "control_ranked": ctl})
    c = pd.DataFrame(rows)
    for col, src in (("v1_hit1", "ranked"), ("v3_hit1", "v3_ranked"), ("control_hit1", "control_ranked")):
        c[col] = [hit_at(x, g, 1) for x, g in zip(c[src], c["gt_service"])]
    out = c.drop(columns=["ranked", "v3_ranked", "control_ranked"]).copy()
    out["v1_top1"] = c["ranked"].map(lambda x: x[0] if x else None)
    save(out, "p2_v1_cases.csv")

    summ = []
    groups = [("ALL", c)] + [("aligned" if a else "misleading", g) for a, g in c.groupby("symptom_aligned")]
    for grp, g in groups:
        sc = {k: score_cases([{"ranked": x, "gt_service": s, "fault": "", "dataset": ds}
                              for x, s, ds in zip(g[k], g["gt_service"], g["dataset"])])
              for k in ("ranked", "v3_ranked", "control_ranked")}
        row = {"group": grp, "n": len(g)}
        for name, k in (("v1", "ranked"), ("v3", "v3_ranked"), ("control", "control_ranked")):
            row.update({f"{name}_AC@1": sc[k]["AC@1"], f"{name}_AC@3": sc[k]["AC@3"], f"{name}_Avg@5": sc[k]["Avg@5"]})
        for other in ("v3", "control"):
            fixed = int((g["v1_hit1"] & ~g[f"{other}_hit1"]).sum())
            broken = int((~g["v1_hit1"] & g[f"{other}_hit1"]).sum())
            row.update({f"v1_fixed_vs_{other}": fixed, f"v1_broken_vs_{other}": broken,
                        f"mcnemar_p_vs_{other}": binomtest(fixed, fixed + broken, 0.5).pvalue if fixed + broken else np.nan})
        summ.append(row)
    s = pd.DataFrame(summ)
    save(s, "p2_v1_summary.csv")
    pd.set_option("display.width", 250)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

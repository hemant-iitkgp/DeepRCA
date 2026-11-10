"""Fair comparison on apps DeepRCA never saw in development (Part 2, Phase 8 / C2; WORKLOG 2026-10-29).

DeepRCA's dev cases were Online Boutique (RE2-OB, RE3-OB), so every OB dataset is excluded here. "Unseen" = the Sock
Shop and Train Ticket datasets (RE1/RE2/RE3 x SS/TT), test cases of waves 1-2 (test_r1).

  baselines   each RCAEval method on the unseen cases it has finished (status ok, or failed = the method's own crash,
              which counts as a miss as in RCAEval); cases still running (status missing) are left out and counted,
              so V3 and the control are scored on exactly the same cases as the method (paired, exact McNemar)
  omnirca     OmniRCA's only real, never-tuned-on dataset in common with ours is RE2-TT; its numbers are transcribed
              from the user's report "OmniRCA Under Test" (n = 28, GPT-4o). Indicative only, different cases.
  rclagent    RCLAgent (Claude-3.5-Sonnet) published only RE2-OB (arXiv:2605.14866v1 Table I); see rclagent_reference.py

Writes results/p2_unseen_baselines.csv (one row per method: n, AC@1/AC@3/Avg@5 of method, V3 and control on the same
cases, fixed/broken/p) and results/p2_unseen_systems.csv (DeepRCA vs OmniRCA vs RCLAgent, each with its control).
Usage: python analysis/p2_unseen_compare.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from p2_common import save
from rca.paths import RESULTS_DIR
from rca.scoring import hit_at, score_cases

UNSEEN = ["RE1-SS", "RE1-TT", "RE2-SS", "RE2-TT", "RE3-SS", "RE3-TT"]
LABEL = {"baro": "BARO", "circa": "CIRCA", "rcd": "RCD", "tracerca": "TraceRCA", "microrank": "MicroRank",
         "pdiagnose": "PDiagnose", "mmbaro": "Multi-source BARO", "mmcirca": "Multi-source CIRCA",
         "mmrcd": "Multi-source RCD"}


def scored(ranked, gt, ds) -> dict:
    return score_cases([{"ranked": r, "gt_service": g, "fault": "", "dataset": d} for r, g, d in zip(ranked, gt, ds)])


def main() -> None:
    ours = pd.read_csv(RESULTS_DIR / "wave_w12_r1_cases.csv")
    ours = ours[ours["dataset"].isin(UNSEEN)].set_index("case_id")
    ours["ranked_v3"] = ours["ranked_v3"].map(json.loads)
    ctrl = pd.read_csv(RESULTS_DIR / "control.csv").set_index("case_id")["ranked_top10"].map(json.loads)
    bl = pd.read_csv(RESULTS_DIR / "baselines.csv")
    bl = bl[bl["dataset"].isin(UNSEEN) & bl["case_id"].isin(ours.index)]
    bl["ranked"] = bl["ranked"].map(json.loads)

    # two views: "rcaeval" counts a method's crash as a miss (RCAEval's rule); "answered" keeps only cases where the
    # method returned a ranking, so a crash we may have caused in setup cannot count against it
    rows = []
    for (m, view), g in [((m, v), g) for m, g in bl.groupby("method") for v in ("rcaeval", "answered")]:
        pending = int((g["status"] == "missing").sum())
        g = g[g["status"] != "missing"] if view == "rcaeval" else g[g["status"] == "ok"]
        if g.empty:
            continue
        o = ours.loc[g["case_id"]]
        sm = scored(g["ranked"], o["gt_service"], o["dataset"])
        sv = scored(o["ranked_v3"], o["gt_service"], o["dataset"])
        sc = scored([ctrl[c] for c in g["case_id"]], o["gt_service"], o["dataset"])
        mh = np.array([hit_at(r, gt, 1) for r, gt in zip(g["ranked"], o["gt_service"])])
        vh = o["v3_hit1"].to_numpy(bool)
        fixed, broken = int((vh & ~mh).sum()), int((~vh & mh).sum())
        rows.append({"method": LABEL.get(m, m), "view": view, "datasets": " ".join(sorted(g["dataset"].unique())), "n": len(g),
                     "pending": pending, "method_failed": int((g["status"] == "failed").sum()),
                     "method_AC@1": sm["AC@1"], "method_AC@3": sm["AC@3"], "method_Avg@5": sm["Avg@5"],
                     "deeprca_AC@1": sv["AC@1"], "deeprca_AC@3": sv["AC@3"], "deeprca_Avg@5": sv["Avg@5"],
                     "control_AC@1": sc["AC@1"], "deeprca_fixed": fixed, "deeprca_broken": broken,
                     "mcnemar_p": binomtest(fixed, fixed + broken, 0.5).pvalue if fixed + broken else np.nan})
    b = pd.DataFrame(rows).sort_values(["view", "method_AC@1"], ascending=[False, False])
    # DeepRCA and control on all unseen cases, for the headline row
    sv = scored(ours["ranked_v3"], ours["gt_service"], ours["dataset"])
    sc = scored([ctrl[c] for c in ours.index], ours["gt_service"], ours["dataset"])
    b = pd.concat([pd.DataFrame([{"method": "DeepRCA (all unseen cases)", "view": "all", "datasets": " ".join(UNSEEN), "n": len(ours),
                                  "pending": 0, "method_failed": 0, "method_AC@1": sv["AC@1"], "method_AC@3": sv["AC@3"],
                                  "method_Avg@5": sv["Avg@5"], "control_AC@1": sc["AC@1"]}]), b], ignore_index=True)
    save(b, "p2_unseen_baselines.csv")

    # the three agent systems, each on data it was not developed on, each against its own statistical control
    tt = ours[ours["dataset"] == "RE2-TT"]
    stt = scored(tt["ranked_v3"], tt["gt_service"], tt["dataset"])
    ctt = scored([ctrl[c] for c in tt.index], tt["gt_service"], tt["dataset"])
    rcl = pd.read_csv(RESULTS_DIR / "rclagent_compare_w12_r1.csv")
    unseen_rcl = rcl[rcl["case_set"].str.startswith("unseen: RE2-SS + RE2-TT")].set_index("method")
    sys_rows = [
        {"system": "DeepRCA", "model": "Gemini 3.7 Flash", "data": "RE2-TT (unseen)", "n": len(tt),
         "AC@1": stt["AC@1"], "control_AC@1": ctt["AC@1"], "source": "results/wave_w12_r1_cases.csv"},
        {"system": "DeepRCA", "model": "Gemini 3.7 Flash", "data": "all 6 unseen datasets", "n": len(ours),
         "AC@1": sv["AC@1"], "control_AC@1": sc["AC@1"], "source": "results/wave_w12_r1_cases.csv"},
        {"system": "DeepRCA", "model": "Gemini 3.7 Flash", "data": "RE2-SS + RE2-TT (unseen)",
         "n": int(unseen_rcl.loc["DeepRCA (V3, Gemini 3.7 Flash)", "n_cases"]),
         "AC@1": unseen_rcl.loc["DeepRCA (V3, Gemini 3.7 Flash)", "R1"] / 100,
         "control_AC@1": unseen_rcl.loc["Control (z-score, BARO-style)", "R1"] / 100,
         "source": "results/rclagent_compare_w12_r1.csv"},
        # transcribed: "OmniRCA Under Test", Results tab (RE2-TT 12 of 28 vs control 17 of 28; pooled real 32/58 vs 38/58)
        {"system": "OmniRCA", "model": "GPT-4o", "data": "RE2-TT (unseen)", "n": 28, "AC@1": 12 / 28,
         "control_AC@1": 17 / 28, "source": "OmniRCA Under Test report (transcribed)"},
        {"system": "OmniRCA", "model": "GPT-4o", "data": "RE2-OB + RE2-TT (unseen)", "n": 58, "AC@1": 32 / 58,
         "control_AC@1": 38 / 58, "source": "OmniRCA Under Test report (transcribed)"},
        # transcribed: arXiv:2605.14866v1 Table I; its RE2-OB was not, as far as the paper says, a tuning set
        {"system": "RCLAgent", "model": "Claude-3.5-Sonnet", "data": "RE2-OB (paper)", "n": 90, "AC@1": 0.5231,
         "control_AC@1": 0.1889, "source": "arXiv:2605.14866v1 Table I (control = its BARO row)"},
    ]
    s = pd.DataFrame(sys_rows)
    s["gain_over_control"] = s["AC@1"] - s["control_AC@1"]
    save(s, "p2_unseen_systems.csv")
    pd.set_option("display.width", 250)
    print(b.round(3).to_string(index=False))
    print()
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

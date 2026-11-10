"""OmniRCA vs DeepRCA, side by side (SPEC 10, "OmniRCA head-to-head"; design-level, not re-run).

OmniRCA was not re-run (user decision 2026-10-28). Its values are transcribed from the user's analysis report
"OmniRCA Under Test" (MTP-1, October 2026): 88 held-out cases (20 synthetic, 30 RE2-OB, 28 RE2-TT), GPT-4o, its own
cases and control. DeepRCA's values are read from our result files (waves 1-2, 339 cases, Gemini 3.7 Flash).
Different cases, models and control runs: the comparison is indicative, never a paired test.

Writes results/p2_omnirca_compare.csv.
Usage: python analysis/p2_omnirca_compare.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RESULTS_DIR  # noqa: E402

SRC = "OmniRCA Under Test (user's report, MTP-1, Oct 2026)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    acc = pd.read_csv(RESULTS_DIR / f"wave_{args.tag}_accuracy.csv")
    row = lambda by, g: acc[(acc["by"] == by) & (acc["group"] == g)].iloc[0]  # noqa: E731
    al, al_m, mi = row("ALL", "ALL"), row("stratum", "aligned"), row("stratum", "misleading")
    tt = row("dataset", "RE2-TT")
    a1 = pd.read_csv(RESULTS_DIR / "p2_a1_summary.csv")
    orig = a1[a1["measure"] == "originates_final_answer"].sort_values("share", ascending=False).iloc[0]
    ov = a1[(a1["measure"] == "draft_vs_evidence_leader") & (a1["group"] == "overrides")].iloc[0]
    a24 = pd.read_csv(RESULTS_DIR / "p2_a24_summary.csv")
    clears = a24[(a24["kind"] == "finding") & (a24["value"] == "clears")].iloc[0]
    refuted = a24[(a24["kind"] == "hypothesis") & (a24["value"] == "refuted")].iloc[0]
    b3 = pd.read_csv(RESULTS_DIR / "p2_b3_summary.csv")
    b3a = b3[b3["scope"] == "all"]
    up = int(b3a[b3a["role"].isin(["upstream caller", "entry point"])]["n"].sum())
    nerr = int(b3a["n"].sum())
    b4 = pd.read_csv(RESULTS_DIR / "p2_b4_predictors.csv")
    r_crowd = b4[(b4["feature"] == "n_anomalous") & (b4["outcome"] == "v3")]["r"].iloc[0]
    comp = pd.read_csv(RESULTS_DIR / "p2_compliance_summary.csv")
    tools = pd.read_csv(RESULTS_DIR / "p2_tools_census.csv")
    ft = pd.read_csv(RESULTS_DIR / f"wave_{args.tag}_faulttype.csv")
    conf = pd.read_csv(RESULTS_DIR / f"wave_{args.tag}_confidence.csv").set_index("bin")
    rows = [
        ("Cases / model", "88 held-out (20 synthetic + 58 RCAEval) / GPT-4o", f"{int(al['n_cases'])} RCAEval test / Gemini 3.7 Flash"),
        ("AC@1 vs control (pooled)", "65.9% vs 70.5%", f"{al['v3_AC@1']:.1%} vs {al['control_AC@1']:.1%}"),
        ("Fixed / broken vs control, McNemar p", "6 / 10, p = 0.455",
         f"{int(al['fixed_vs_control'])} / {int(al['broken_vs_control'])}, p = {al['mcnemar_p']:.2g}"),
        ("Misleading cases: system vs control", "37.5% vs 12.5% (n = 16), p = 0.125",
         f"{mi['v3_AC@1']:.1%} vs {mi['control_AC@1']:.1%} (n = {int(mi['n_cases'])}), p = {mi['mcnemar_p']:.2g}"),
        ("Aligned cases: system vs control", "72.2% vs 83.3% (n = 72), 10 broken, p = 0.039",
         f"{al_m['v3_AC@1']:.1%} vs {al_m['control_AC@1']:.1%} (n = {int(al_m['n_cases'])}), "
         f"{int(al_m['broken_vs_control'])} broken, p = {al_m['mcnemar_p']:.2g}"),
        ("RE2-TT AC@1 vs control", "42.9% vs 60.7% (n = 28)", f"{tt['v3_AC@1']:.1%} vs {tt['control_AC@1']:.1%} (n = {int(tt['n_cases'])})"),
        ("Who decides (A1)", "first agent originates 82%; five others net +3 cases in 72 runs",
         f"largest originator {orig['group']} {orig['share']:.1%}; main agent overrides of the evidence leader fixed "
         f"{int(ov['fixed_by_override'])}, broke {int(ov['broken_by_override'])}"),
        ("Disconfirming evidence (A2.4)", "0 of 329 items",
         f"{int(clears['n'])} findings clear their suspect ({clears['share']:.1%}); {int(refuted['n'])} hypotheses refuted ({refuted['share']:.1%})"),
        ("Errors blaming a caller / entry point (B3)", "23 of 30 (77%)", f"{up} of {nerr} ({up / nerr:.0%})"),
        ("Success vs number of anomalous services (B4)", "r = -0.34", f"r = {r_crowd:.2f}"),
        ("Prompt-rule compliance", "69.8% to 100%", f"{comp['compliance'].min():.1%} to {comp['compliance'].max():.1%}"),
        ("Tools never called", "7 of 24", f"{int((tools['calls'] == 0).sum())} of {len(tools)}"),
        ("Fault-type accuracy", "10-30%", f"{ft[ft['by'] == 'ALL']['fault_type_accuracy'].iloc[0]:.1%}"),
        ("Confidence", "agreement-based; HIGH 90% right on synthetic, 48% on TT",
         f"evidence-based; AUROC {conf.loc['AUROC', 'mean_confidence']:.2f}"),
    ]
    out = pd.DataFrame(rows, columns=["measure", "OmniRCA", "DeepRCA"])
    out["omnirca_source"] = SRC
    out.to_csv(RESULTS_DIR / "p2_omnirca_compare.csv", index=False)
    pd.set_option("display.width", 250, "display.max_colwidth", 90)
    print(out.drop(columns="omnirca_source").to_string(index=False))


if __name__ == "__main__":
    main()

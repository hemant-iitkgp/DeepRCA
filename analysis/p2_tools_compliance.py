"""Tool use and instruction compliance from the transcripts (OmniRCA report C4.2 and its tool census; Part 3 G2-G3)

Tool census: calls per (agent, tool) over all cases, and which registered tools were never called.
Compliance: per case, whether the main agent did what its prompt (prompts/main_v1.md) asks, checked from its calls:
  first_data_tool_ok        first data tool is select_traces (case has traces) or anomalous_services (no traces)
  wrote_todos               called write_todos
  called_candidate_rank     called candidate_rank (step 5)
  summary_before_draft      called evidence_summary before its first write_draft (step 6)
  fault_indicators_on_top   called fault_indicators on the service it finally ranked first (step 6)
  critic_once               launched the critic exactly once (step 7)
Rules that code enforces (coverage, locking, structured answers) are not listed: they cannot be broken.

Writes results/p2_tools_census.csv, results/p2_compliance_cases.csv, results/p2_compliance_summary.csv.
Usage: python analysis/p2_tools_compliance.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import pandas as pd

from p2_common import load_cases, save, tool_calls
from rca.agent.tools import CRITIC_TOOLS, INVESTIGATOR_TOOLS, MAIN_TOOLS, TESTER_TOOLS

DATA_TOOLS = {"select_traces", "anomalous_services"}


def _inp(x) -> dict:
    if isinstance(x, dict):
        return x
    try:
        return json.loads(str(x).replace("'", '"'))
    except Exception:
        return {"raw": str(x)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    census: Counter = Counter()
    comp = []
    for r in d.itertuples():
        calls = tool_calls(r.run_dir)
        for c in calls:
            census[(c["agent"], c["tool"])] += 1
        main_calls = [c for c in calls if c["agent"] == "main"]
        names = [c["tool"] for c in main_calls]
        has_traces = json.loads((r.run_dir / "result.json").read_text()).get("selected_traces", 0) > 0 or \
            "select_traces" in names and "anomalous_services" not in names
        first_data = next((n for n in names if n in DATA_TOOLS), None)
        tasks = [_inp(c["input"]) for c in main_calls if c["tool"] == "task"]
        critic_n = sum(1 for t in tasks if str(t.get("subagent_type", t.get("raw", ""))).find("critic") >= 0)
        top = r.ranked_v3[0] if r.ranked_v3 else None
        fi_top = any(c["tool"] == "fault_indicators" and _inp(c["input"]).get("service") == top for c in main_calls)
        i_draft = names.index("write_draft") if "write_draft" in names else None
        comp.append({"case_id": r.case_id, "dataset": r.dataset,
                     "first_data_tool_ok": first_data == ("select_traces" if has_traces else "anomalous_services"),
                     "wrote_todos": "write_todos" in names, "called_candidate_rank": "candidate_rank" in names,
                     "summary_before_draft": i_draft is not None and "evidence_summary" in names[:i_draft],
                     "fault_indicators_on_top": fi_top, "critic_once": critic_n == 1, "critic_launches": critic_n})
    cs = pd.DataFrame([{"agent": a, "tool": t, "calls": n} for (a, t), n in sorted(census.items())])
    registered = {("main", t) for t in MAIN_TOOLS} | {("span-investigator", t) for t in INVESTIGATOR_TOOLS} | \
        {("hypothesis-tester", t) for t in TESTER_TOOLS} | {("critic", t) for t in CRITIC_TOOLS}
    never = sorted(registered - set(census))
    cs = pd.concat([cs, pd.DataFrame([{"agent": a, "tool": t, "calls": 0} for a, t in never])], ignore_index=True)
    save(cs, "p2_tools_census.csv")
    c = pd.DataFrame(comp)
    save(c, "p2_compliance_cases.csv")
    rules = ["first_data_tool_ok", "wrote_todos", "called_candidate_rank", "summary_before_draft",
             "fault_indicators_on_top", "critic_once"]
    s = pd.DataFrame([{"rule": k, "compliance": c[k].mean(), "n": len(c)} for k in rules])
    save(s, "p2_compliance_summary.csv")
    pd.set_option("display.width", 200)
    print(s.round(3).to_string(index=False))
    print("never called:", never)


if __name__ == "__main__":
    main()

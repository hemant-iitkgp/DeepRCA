"""B3: error taxonomy (SPEC 10, theme B; OmniRCA: 23 of 30 errors blamed a caller of the culprit)

For every case whose V3 #1 is wrong, the blamed service's role relative to the true root cause in the case's call
graph (rca.tools.topology.case_graph; edges point caller -> callee):
  entry point          blamed has no callers and reaches the true cause
  upstream caller      a call path blamed -> ... -> true exists
  downstream dependency a call path true -> ... -> blamed exists
  sibling              no path either way, but they share a caller
  unrelated            none of the above
  no call graph        the app has no call graph (Sock Shop)
plus the hop distance in the undirected graph, and whether the true cause was elsewhere in the top 5.

Writes results/p2_b3_errors.csv and results/p2_b3_summary.csv.
Usage: python analysis/p2_b3_errors.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse

import networkx as nx
import pandas as pd

from p2_common import load_cases, save
from rca.tools.data import CaseData
from rca.tools.topology import case_graph


def role(g: nx.DiGraph, blamed: str, true: str) -> str:
    if g.number_of_edges() == 0:
        return "no call graph"
    if blamed not in g or true not in g:
        return "not in graph"
    if nx.has_path(g, blamed, true):
        return "entry point" if g.in_degree(blamed) == 0 else "upstream caller"
    if nx.has_path(g, true, blamed):
        return "downstream dependency"
    if set(g.predecessors(blamed)) & set(g.predecessors(true)):
        return "sibling"
    return "unrelated"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    rows = []
    for r in d[~d["v3_hit1"]].itertuples():
        g = case_graph(CaseData(r.dataset, r.case_id))
        blamed = r.ranked_v3[0] if r.ranked_v3 else None
        true = r.gt_service
        hops = None
        if blamed and g.number_of_edges() and blamed in g and true in g:
            u = g.to_undirected()
            hops = nx.shortest_path_length(u, blamed, true) if nx.has_path(u, blamed, true) else None
        rows.append({"case_id": r.case_id, "dataset": r.dataset, "system": r.system, "symptom_aligned": r.symptom_aligned,
                     "true": true, "blamed": blamed, "role": role(g, blamed, true) if blamed else "no answer",
                     "hops": hops, "true_in_top5": true in (r.ranked_v3 or [])[:5]})
    e = pd.DataFrame(rows)
    save(e, "p2_b3_errors.csv")
    s = (e.groupby(["role"]).agg(n=("case_id", "size"), median_hops=("hops", "median"),
                                 true_in_top5=("true_in_top5", "mean")).reset_index())
    s["share"] = s["n"] / len(e)
    s2 = e.groupby(["system", "role"]).size().rename("n").reset_index()
    s2["role"] = s2["system"] + ": " + s2["role"]
    out = pd.concat([s.assign(scope="all"), s2[["role", "n"]].assign(scope="by app")], ignore_index=True)
    save(out, "p2_b3_summary.csv")
    pd.set_option("display.width", 200)
    print(f"{len(e)} wrong top-1 answers")
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

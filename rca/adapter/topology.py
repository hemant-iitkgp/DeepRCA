"""Build static call graphs per system from normal-period (baseline window) traces of RE2/RE3.

Usage: python -m rca.adapter.topology [--workers 16]
Writes data/topology/<system>.json: {"services", "edges": [[caller, callee, n_cases]], "source", "n_cases"}
and results/topology_summary.csv. Systems without traces get an empty graph with source "none".
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from rca.paths import CANONICAL_DIR, RESULTS_DIR, TOPOLOGY_DIR
from rca.tools.data import CaseData
from rca.tools.traces import span_table


def _edges(args) -> tuple[str, set, set]:
    ds, cid = args
    cd = CaseData(ds, cid)
    services = set(cd.services)
    if not cd.case["has_traces"]:
        return cd.case["system"], set(), services
    s = span_table(cd)
    b0, b1 = cd.baseline()
    s = s[(s["ts_start"] >= b0) & (s["ts_start"] < b1)]
    e = set(map(tuple, s.loc[s["is_cross_call"], ["caller_service", "service"]].drop_duplicates().values))
    e |= set(map(tuple, s.loc[s["callee"].notna(), ["service", "callee"]].drop_duplicates().values))
    return cd.case["system"], {x for x in e if x[0] != x[1]}, services


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    jobs = []
    for ds_dir in sorted(CANONICAL_DIR.iterdir()):
        if ds_dir.name.startswith(("RE2", "RE3")):
            jobs += [(ds_dir.name, c.name) for c in sorted(ds_dir.iterdir()) if (c / "case.json").exists()]
    edges: dict[str, Counter] = {}
    services: dict[str, set] = {}
    ncases: Counter = Counter()
    with ProcessPoolExecutor(args.workers) as ex:
        for system, e, svcs in ex.map(_edges, jobs, chunksize=2):
            edges.setdefault(system, Counter()).update(e)
            services.setdefault(system, set()).update(svcs)
            if e:
                ncases[system] += 1
    TOPOLOGY_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for system in sorted(services):
        es = sorted([[a, b, n] for (a, b), n in edges.get(system, Counter()).items()])
        out = {"system": system, "services": sorted(services[system]), "edges": es,
               "source": "baseline-window traces of RE2/RE3" if es else "none", "n_cases_with_traces": ncases[system]}
        (TOPOLOGY_DIR / f"{system}.json").write_text(json.dumps(out, indent=1))
        rows.append({"system": system, "services": len(services[system]), "edges": len(es),
                     "cases_with_traces": ncases[system], "source": out["source"]})
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "topology_summary.csv", index=False)
    print(pd.DataFrame(rows).to_string())


if __name__ == "__main__":
    main()

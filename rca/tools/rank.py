"""candidate_rank: the control's ranking and RCAEval's BARO ranking (SPEC 7.2).

BARO is called through RCAEval's library (`RCAEval.e2e.baro`) on the case's service-level
metrics in the same wide layout RCAEval's main.py feeds it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from rca.control.zscore import control_rank
from rca.tools.cache import cached
from rca.tools.data import CaseData


def baro_input(cd: CaseData) -> pd.DataFrame:
    m = cd.metrics
    m = m[m["entity_level"] == "service"]
    src = "derived" if (m["source"] == "derived").any() else "raw"
    m = m[m["source"] == src]
    b0, _ = cd.baseline()
    _, w1 = cd.window()
    m = m[(m["ts"] >= b0) & (m["ts"] <= w1)]
    wide = m.assign(col=m["entity"] + "_" + m["metric"]).pivot_table(index="ts", columns="col", values="value")
    wide = wide.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    wide.insert(0, "time", wide.index.astype(np.int64))
    return wide.reset_index(drop=True)


def _baro(cd: CaseData) -> dict:
    from RCAEval.e2e import baro

    data = baro_input(cd)
    ranks = baro(data, cd.fault_start, dataset="canonical")["ranks"]
    services, seen = [], set()
    for r in ranks:
        s = r.split("_")[0]
        if s not in seen:
            seen.add(s)
            services.append(s)
    return {"ranked_services": services, "ranked_indicators": ranks[:20]}


def baro_rank(cd: CaseData) -> dict:
    return cached(cd.cache_key, "baro", {"fs": cd.fault_start}, lambda: _baro(cd))


def candidate_rank(cd: CaseData, k: int = 10) -> dict:
    c = control_rank(cd)
    b = baro_rank(cd)
    return {
        "control_zscore": [{"service": s, "max_z": round(z, 1), "metric": m}
                           for s, z, m in list(zip(c["ranked"], c["scores"], c["top_metric"]))[:k]],
        "baro": b["ranked_services"][:k],
        "note": "statistical rankings are hints only; the loudest metric is often a symptom, not the cause",
    }

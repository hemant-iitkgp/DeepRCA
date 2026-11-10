"""metric_anomalies: metrics of one entity that deviate beyond n-sigma from the baseline window."""
from __future__ import annotations

import numpy as np
import pandas as pd

from rca.paths import system_config
from rca.tools.cache import cached
from rca.tools.data import CaseData


def _stats(cd: CaseData) -> pd.DataFrame:
    m = cd.metrics
    b0, b1 = cd.baseline()
    return m[(m["ts"] >= b0) & (m["ts"] < b1)].groupby(["entity", "metric"])["value"].agg(["mean", "std"])


def baseline_stats(cd: CaseData) -> pd.DataFrame:
    return cached(cd.cache_key, "metric_baseline", {"b": cd.baseline()}, lambda: _stats(cd))


def entity_anomalies(cd: CaseData, entity: str, t_from: float, t_to: float, n_sigma: float) -> list[dict]:
    m = cd.metrics
    m = m[(m["entity"] == entity) & (m["ts"] >= t_from) & (m["ts"] <= t_to)]
    if m.empty:
        return []
    st = baseline_stats(cd)
    fs = cd.fault_start
    out = []
    for (ent, met), g in m.groupby(["entity", "metric"]):
        if (ent, met) not in st.index:
            continue
        mu, sd = st.loc[(ent, met), "mean"], st.loc[(ent, met), "std"]
        if not np.isfinite(sd) or sd <= system_config()["control"]["min_baseline_std"]:
            continue
        g = g.dropna(subset=["value"]).sort_values("ts")
        if g.empty:
            continue
        z = (g["value"].values - mu) / sd
        az = np.abs(z)
        if az.max() <= n_sigma:
            continue
        i_peak = int(az.argmax())
        onset = g["ts"].values[int(np.argmax(az > n_sigma))]
        bins = np.array_split(g["value"].values, min(10, len(g)))
        out.append({
            "entity": ent, "metric": met, "type": g["metric_type"].iloc[0],
            "direction": "up" if z[i_peak] > 0 else "down",
            "peak_z": round(float(az[i_peak]), 1),
            "onset_s_after_fault": int(onset - fs),
            "baseline_mean": float(f"{mu:.4g}"),
            "curve10": [float(f"{np.nanmean(b):.4g}") for b in bins],
        })
    return sorted(out, key=lambda r: -r["peak_z"])


RESOURCE_TYPES = {"cpu", "memory", "disk", "network"}
Z_DISPLAY_CAP = 100.0


def _display(a: dict) -> dict:
    a = dict(a)
    if a["peak_z"] > Z_DISPLAY_CAP:
        a["peak_z"] = Z_DISPLAY_CAP
        a["peak_z_capped"] = True
    return a


def metric_anomalies(cd: CaseData, entity: str, level: str = "service", t0: float | None = None,
                     delta: float | None = None, limit: int = 10) -> dict:
    cfg = system_config()["tools"]
    n = cfg["metric_n_sigma"]
    w0, w1 = cd.window()
    if t0 is not None:
        delta = delta or cfg["metric_delta_s"]
        t_from, t_to = max(w0 - delta, t0 - delta), min(w1, t0 + delta)
    else:
        t_from, t_to = w0, w1
    known = set(cd.metrics["entity"].unique())
    if entity not in known:
        return {"entity": entity, "error": "no metrics for this entity", "known_entities_sample": sorted(known)[:40]}
    res = [_display(a) for a in entity_anomalies(cd, entity, t_from, t_to, n)]
    # latency/error/throughput can be produced by callers, callees or the network; resource metrics are the
    # entity's own consumption. They are shown apart so a symptom metric is not read as the entity's own fault.
    own = [a for a in res if a["type"] in RESOURCE_TYPES]
    sym = [a for a in res if a["type"] not in RESOURCE_TYPES]
    out = {"entity": entity, "level": level, "window_s_after_fault": [int(t_from - cd.fault_start), int(t_to - cd.fault_start)],
           "n_sigma": n,
           "resource_metrics": own[:limit],
           "latency_error_traffic_metrics": sym[: max(3, limit - len(own[:limit]))],
           "note": "latency/error/traffic metrics can be caused by callers, callees or the network path; "
                   "z above 100 is shown as 100 (tiny baseline variance)",
           "n_anomalous_metrics": len(res)}
    if level == "service":
        ent = cd.entities
        nodes = sorted(ent.loc[(ent["service"] == entity) & ent["node"].notna(), "node"].unique())
        node_res = []
        for nd in nodes:
            node_res += entity_anomalies(cd, nd, t_from, t_to, n)[:4]
        out["node_metrics"] = node_res[:6] if nodes else "no node information for this entity"
    return out

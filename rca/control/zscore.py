"""The no-LLM statistical control (SPEC 1.3, Phase 2).

Implemented from the SPEC's definition alone (the user asked for no OmniRCA influence;
see WORKLOG 2026-10-24): for every service-level metric channel, z = |x - mean_b| / std_b
against the pre-fault baseline window; a channel's score is its largest z inside the
analysis window; a service's score is the maximum over its channels; services are ranked
by score and top-1 is the answer. A service is "anomalous" when its score exceeds 2.5.
"""
from __future__ import annotations

import pandas as pd

from rca.paths import system_config
from rca.tools.data import CaseData


def channel_scores(cd: CaseData, level: str = "service") -> pd.DataFrame:
    """One row per (entity, metric): baseline mean/std, peak |z| in the window, time of the peak."""
    cfg = system_config()["control"]
    m = cd.metrics
    m = m[m["entity_level"] == level]
    b0, b1 = cd.baseline()
    w0, w1 = cd.window()
    base = m[(m["ts"] >= b0) & (m["ts"] < b1)].groupby(["entity", "metric"])["value"].agg(["mean", "std", "count"])
    win = m[(m["ts"] >= w0) & (m["ts"] <= w1)][["entity", "metric", "ts", "value"]]
    win = win.join(base, on=["entity", "metric"], how="inner")
    win = win[(win["std"] > cfg["min_baseline_std"]) & win["value"].notna()]
    win["z"] = (win["value"] - win["mean"]).abs() / win["std"]
    if win.empty:
        return pd.DataFrame(columns=["entity", "metric", "z", "peak_ts", "mean", "std"])
    idx = win.groupby(["entity", "metric"])["z"].idxmax()
    out = win.loc[idx, ["entity", "metric", "z", "ts", "mean", "std"]].rename(columns={"ts": "peak_ts"})
    return out.reset_index(drop=True)


def control_rank(cd: CaseData) -> dict:
    """Returns ranked services with scores and the gate statistics (SPEC 7.8)."""
    z_thr = system_config()["control"]["z_anomalous"]
    ch = channel_scores(cd, "service")
    if ch.empty:
        svc = pd.DataFrame(columns=["entity", "z", "metric"])
    else:
        best = ch.loc[ch.groupby("entity")["z"].idxmax()]
        svc = best[["entity", "z", "metric"]].sort_values(["z", "entity"], ascending=[False, True])
    # services without any usable channel go last, in name order
    missing = sorted(set(cd.services) - set(svc["entity"]))
    ranked = list(svc["entity"]) + missing
    scores = list(svc["z"].astype(float)) + [0.0] * len(missing)
    top_metric = list(svc["metric"]) + [None] * len(missing)
    n_anom = int((svc["z"] > z_thr).sum())
    margin = float(scores[0] - scores[1]) if len(scores) > 1 else float("inf")
    ratio = float(scores[0] / scores[1]) if len(scores) > 1 and scores[1] > 0 else float("inf")
    return {
        "ranked": ranked,
        "scores": scores,
        "top_metric": top_metric,
        "n_anomalous": n_anom,
        "z_margin": margin,
        "z_ratio": ratio,
        "top1_z": float(scores[0]) if scores else 0.0,
    }


def ranked_indicators(cd: CaseData, k: int = 10) -> list[str]:
    """Control's indicator ranking: service_<metric> by channel z (used only as a fallback tail)."""
    ch = channel_scores(cd, "service").sort_values("z", ascending=False)
    return [f"{e}_{m}" for e, m in zip(ch["entity"], ch["metric"])][:k]

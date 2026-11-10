"""Fault onset detection for the `fault_time: detect` run (SPEC 3.1 rule 2).

Without the injection time: take the first third of the data as a reference period, score every
service-level channel against it, count per second the channels beyond n-sigma, and call the onset
the first time this count stays above the reference period's own level (mean + 3 sd) for `sustain`
seconds. Windows are then rebuilt around the detected onset exactly as for a provided fault time.
"""
from __future__ import annotations

import numpy as np

from rca.paths import system_config
from rca.tools.data import CaseData


def detect_onset(cd: CaseData, n_sigma: float = 3.0, sustain: int = 10) -> dict:
    m = cd.metrics
    m = m[m["entity_level"] == "service"]
    t_min, t_max = cd.case["data_start"], cd.case["data_end"]
    ref_end = t_min + (t_max - t_min) / 3.0
    ref = m[m["ts"] < ref_end].groupby(["entity", "metric"])["value"].agg(["mean", "std"])
    ref = ref[ref["std"] > system_config()["control"]["min_baseline_std"]]
    x = m.join(ref, on=["entity", "metric"], how="inner")
    x["anom"] = ((x["value"] - x["mean"]).abs() / x["std"]) > n_sigma
    counts = x.groupby("ts")["anom"].sum().sort_index()
    rc = counts[counts.index < ref_end]
    thr = float(rc.mean() + 3 * rc.std()) if len(rc) > 1 else float(rc.mean() if len(rc) else 0)
    after = counts[counts.index >= ref_end]
    above = (after > thr).astype(int).rolling(sustain).sum() >= sustain
    if above.any():
        onset = int(above.idxmax()) - sustain + 1
        found = True
    else:
        onset = int(after.idxmax()) if len(after) else int(ref_end)
        found = False
    w = system_config()["window"]
    override = {"fault_start": onset, "baseline_start": max(t_min, onset - w["baseline_seconds"]), "baseline_end": onset,
                "window_start": onset, "window_end": min(t_max, onset + w["analysis_seconds"])}
    return {"detected_onset": onset, "found": found, "threshold": round(thr, 2), "case_override": override}

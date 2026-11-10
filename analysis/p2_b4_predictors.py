"""B4: what predicts failure? (SPEC 10, theme B; OmniRCA: success r = -0.34 with the number of anomalous services)

Per case features, all computed by code before or during the run:
  n_anomalous     services the control scores above z 2.5 (results/control.csv)
  z_margin_log    log10(1 + control top-1 minus top-2 score)
  n_services      candidate services in the case
  has_traces      the case has traces
  work_items      suspects registered for investigation (result.json)
  subagents       helper launches
Point-biserial correlation (Pearson r with a 0/1 outcome) of each feature with V3 top-1 success and with control
success, plus V3 accuracy by tercile of n_anomalous.

Writes results/p2_b4_predictors.csv.
Usage: python analysis/p2_b4_predictors.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from p2_common import load_cases, save
from rca.paths import RESULTS_DIR


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    ctrl = pd.read_csv(RESULTS_DIR / "control.csv").set_index("case_id")
    d["n_anomalous"] = d["case_id"].map(ctrl["n_anomalous"])
    d["z_margin_log"] = np.log10(1 + d["case_id"].map(ctrl["z_margin"]).clip(lower=0))
    d["n_services"] = d["case_id"].map(ctrl["n_services"])
    res = {c: json.loads((rd / "result.json").read_text()) for c, rd in zip(d["case_id"], d["run_dir"])}
    d["work_items"] = d["case_id"].map(lambda c: res[c].get("work_items"))
    d["subagents"] = d["case_id"].map(lambda c: res[c].get("subagent_launches"))
    d["has_traces"] = d["case_id"].map(lambda c: float(res[c].get("selected_traces", 0) > 0))
    rows = []
    for f in ("n_anomalous", "z_margin_log", "n_services", "has_traces", "work_items", "subagents"):
        x = d[f].astype(float)
        for who, y in (("v3", d["v3_hit1"]), ("control", d["control_hit1"])):
            m = x.notna()
            r = float(np.corrcoef(x[m], y[m].astype(float))[0, 1]) if x[m].std() > 0 else np.nan
            rows.append({"feature": f, "outcome": who, "r": r, "n": int(m.sum())})
    d["crowding"] = pd.qcut(d["n_anomalous"], 3, labels=["few", "middle", "many"], duplicates="drop")
    for k, g in d.groupby("crowding", observed=True):
        rows.append({"feature": f"n_anomalous tercile: {k} ({int(g['n_anomalous'].min())}-{int(g['n_anomalous'].max())})",
                     "outcome": "accuracy", "r": None, "n": len(g), "v3_AC@1": g["v3_hit1"].mean(),
                     "control_AC@1": g["control_hit1"].mean()})
    out = pd.DataFrame(rows)
    save(out, "p2_b4_predictors.csv")
    pd.set_option("display.width", 200)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()

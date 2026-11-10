"""Write data/splits.csv once (SPEC 3.2). Refuses to overwrite an existing file.

Dev: about 60 cases from RE2-OB and RE3-OB, stratified by fault type (7 per fault type in RE2-OB,
18 spread over the fault types of RE3-OB), spread across injected services, fixed seed.
Test: every other case of all 9 datasets.

Usage: python -m rca.adapter.splits
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from rca.adapter.layout import case_id_for, list_raw_cases, parse_folder
from rca.paths import DATASETS, SPLITS_CSV

SEED = 20261024
DEV_QUOTA = {"RE2-OB": 42, "RE3-OB": 18}


def collect() -> pd.DataFrame:
    """Built from the raw folder layout (same opaque case IDs as the adapter), so splits exist
    before any case output is inspected."""
    rows = []
    for ds in DATASETS:
        cases, _ = list_raw_cases(ds)
        for c in cases:
            f = parse_folder(c.parent.name)
            rows.append({"case_id": case_id_for(ds, c), "dataset": ds, "system": ds.split("-")[1],
                         "fault_type": f["fault"], "service": f["service"]})
    return pd.DataFrame(rows)


def pick(df: pd.DataFrame, n: int, rng: np.random.Generator) -> list[str]:
    faults = sorted(df["fault_type"].unique())
    per = {f: n // len(faults) for f in faults}
    for f in faults[: n - sum(per.values())]:
        per[f] += 1
    chosen = []
    for f in faults:
        g = df[df["fault_type"] == f].copy()
        g["r"] = rng.random(len(g))
        # round-robin over services so dev covers as many injected services as possible
        g = g.sort_values(["service", "r"])
        g["k"] = g.groupby("service").cumcount()
        g = g.sort_values(["k", "r"])
        chosen += list(g["case_id"].head(per[f]))
    return chosen


def main() -> None:
    if SPLITS_CSV.exists():
        print(f"{SPLITS_CSV} exists and must never change after creation; not overwriting.")
        sys.exit(1)
    df = collect()
    rng = np.random.default_rng(SEED)
    dev = []
    for ds, n in DEV_QUOTA.items():
        dev += pick(df[df["dataset"] == ds], n, rng)
    df["split"] = np.where(df["case_id"].isin(dev), "dev", "test")
    df = df.drop(columns=["service"]).sort_values(["dataset", "case_id"])
    df.to_csv(SPLITS_CSV, index=False)
    print(df.groupby(["dataset", "split"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()

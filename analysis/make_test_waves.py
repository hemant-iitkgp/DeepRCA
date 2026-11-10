"""Split the test cases into 4 waves so that partial results are representative (user request, 2026-10-26).

Each wave is a stratified random quarter of the test split: within every (dataset, fault type) stratum the
cases are shuffled with a fixed seed and dealt round-robin to waves 1-4, with the starting wave rotated
per stratum so small strata do not always fill wave 1. Any completed wave therefore covers all 9 datasets and
their fault types in the same proportions as the full test set. data/splits.csv is not changed.

Writes data/test_waves.csv (case_id, dataset, system, fault_type, wave) and results/test_waves_summary.csv.
Refuses to overwrite an existing waves file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import DATA_DIR, RESULTS_DIR, SPLITS_CSV  # noqa: E402

SEED = 20261026
N_WAVES = 4
OUT = DATA_DIR / "test_waves.csv"


def main() -> None:
    if OUT.exists():
        print(f"{OUT} exists and must not change once runs have started; not overwriting.")
        sys.exit(1)
    sp = pd.read_csv(SPLITS_CSV)
    test = sp[sp["split"] == "test"].sort_values(["dataset", "fault_type", "case_id"]).reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    waves = []
    for i, ((ds, ft), g) in enumerate(test.groupby(["dataset", "fault_type"], sort=True)):
        order = rng.permutation(len(g))
        start = i % N_WAVES
        for k, idx in enumerate(order):
            waves.append((g.iloc[idx]["case_id"], (start + k) % N_WAVES + 1))
    w = test.merge(pd.DataFrame(waves, columns=["case_id", "wave"]), on="case_id")
    w[["case_id", "dataset", "system", "fault_type", "wave"]].to_csv(OUT, index=False)
    summ = w.pivot_table(index="dataset", columns="wave", values="case_id", aggfunc="count", fill_value=0)
    summ["total"] = summ.sum(axis=1)
    summ.loc["ALL"] = summ.sum()
    summ.to_csv(RESULTS_DIR / "test_waves_summary.csv")
    print(summ.to_string())
    print(w.pivot_table(index="fault_type", columns="wave", values="case_id", aggfunc="count", fill_value=0).to_string())


if __name__ == "__main__":
    main()

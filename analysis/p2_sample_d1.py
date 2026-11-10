"""D1 subset for the stability re-run (Part 2; added 2026-10-28 for the OmniRCA comparison, which reports stability).

Every third case of data/p2_sample.csv (sorted by dataset and case ID) -> data/p2_d1_cases.csv (34 cases, all datasets).
The frozen system is re-run unchanged on these cases under run id p2_rerun; analysis compares each case's answer with
its run-1 answer in test_r1. Written once.

Usage: python analysis/p2_sample_d1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import DATA_DIR  # noqa: E402


def main() -> None:
    out = DATA_DIR / "p2_d1_cases.csv"
    if out.exists():
        print(f"{out} exists; not redrawn")
        return
    s = pd.read_csv(DATA_DIR / "p2_sample.csv").sort_values(["dataset", "case_id"]).reset_index(drop=True)
    d1 = s.iloc[::3]
    d1.to_csv(out, index=False)
    print(d1.groupby("dataset").size().to_string())


if __name__ == "__main__":
    main()

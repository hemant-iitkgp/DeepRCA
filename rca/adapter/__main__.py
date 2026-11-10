"""Convert raw RCAEval cases to the canonical schema.

Usage: python -m rca.adapter [--datasets RE2-OB RE3-OB ...] [--workers 16] [--overwrite] [--limit N]
Writes results/adapter_report.csv (one row per case).
"""
from __future__ import annotations

import argparse
import json
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

from rca.adapter.convert import convert_case
from rca.adapter.layout import list_raw_cases
from rca.paths import DATASETS, RESULTS_DIR


def _one(args):
    ds, case_dir, overwrite = args
    try:
        return convert_case(ds, case_dir, overwrite=overwrite)
    except Exception as e:  # recorded, never hidden
        return {"dataset": ds, "case_dir": str(case_dir), "ok": False, "error": repr(e), "trace": traceback.format_exc()[-2000:]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", nargs="*", default=DATASETS)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    jobs = []
    for ds in args.datasets:
        cases, _ = list_raw_cases(ds)
        jobs += [(ds, c, args.overwrite) for c in cases[: args.limit]]
    rows = []
    with ProcessPoolExecutor(args.workers) as ex:
        futs = [ex.submit(_one, j) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            rows.append(r)
            print(f"[{i}/{len(jobs)}] {r.get('dataset')} {r.get('case_id', r.get('case_dir'))} ok={r.get('ok')}"
                  + ("" if r.get("ok") else f" {r.get('error')}"), flush=True)
    df = pd.DataFrame([{k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()} for r in rows])
    RESULTS_DIR.mkdir(exist_ok=True)
    name = "adapter_report.csv" if set(args.datasets) == set(DATASETS) and not args.limit else "adapter_report_partial.csv"
    df.sort_values(["dataset", "case_id"] if "case_id" in df else ["dataset"]).to_csv(RESULTS_DIR / name, index=False)
    print(df["ok"].value_counts())


if __name__ == "__main__":
    main()

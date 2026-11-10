"""Run RCAEval's own baselines with its unmodified main.py (Part 2, Phase 6 step 2).

For each (method, dataset) a working folder runs/rcaeval/<tag>/<method>/<dataset>/ gets a `data/` tree of symlinks in
the layout main.py expects (DATASET_MAP), pointing at our raw RCAEval download, and main.py runs there with its
default settings (--length 20: 10 minutes either side of the injection). main.py writes one
output/results/<service>_<fault>_<rep>.json per case; analysis/baselines_collect.py maps those to our case IDs.

Folders main.py cannot parse are left out of the view and listed in skipped.json: main.py splits the fault folder
name on "_" into exactly (service, fault), so a folder with a variant suffix ("<service>_f3_1") would stop the run.

Usage: python baselines/run_rcaeval.py --methods baro circa --datasets re2-ob re2-tt [--workers 6] [--test]
       [--cases data/test_waves.csv --waves 1 2 --tag w12]   (only those cases)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rca.paths import RAW_DIR, RUNS_DIR  # noqa: E402

RCAEVAL = Path(os.environ.get("RCAEVAL_SRC", Path.home() / "src" / "RCAEval"))
# main.py's DATASET_MAP target for each dataset, relative to the working folder
TARGET = {"re1-ob": "data/online-boutique", "re1-ss": "data/sock-shop-2", "re1-tt": "data/train-ticket",
          "re2-ob": "data/RE2/RE2-OB", "re2-ss": "data/RE2/RE2-SS", "re2-tt": "data/RE2/RE2-TT",
          "re3-ob": "data/RE3/RE3-OB", "re3-ss": "data/RE3/RE3-SS", "re3-tt": "data/RE3/RE3-TT"}


def build_view(work: Path, dataset: str, cases: set[str] | None = None) -> list[str]:
    """Symlink the raw dataset's case folders into work/<TARGET> (only `cases`, when given); return the
    fault folders left out because main.py cannot parse their name."""
    from rca.adapter.layout import case_id_for

    src = RAW_DIR / dataset.upper()
    dst = work / TARGET[dataset]
    dst.mkdir(parents=True, exist_ok=True)
    skipped = []
    for f in sorted(p for p in src.iterdir() if p.is_dir()):
        if len(f.name.split("_")) != 2:
            skipped.append(f.name)
            continue
        for rep in sorted(r for r in f.iterdir() if r.is_dir() and r.name.isdigit()):
            if cases is not None and case_id_for(dataset.upper(), rep) not in cases:
                continue
            link = dst / f.name / rep.name
            link.parent.mkdir(exist_ok=True)
            if not link.exists():
                link.symlink_to(rep)
    return skipped


def run_one(method: str, dataset: str, test: bool, python: str, cases: set[str] | None = None, tag: str = "") -> dict:
    work = RUNS_DIR / "rcaeval" / (tag or "all") / method / dataset
    work.mkdir(parents=True, exist_ok=True)
    skipped = build_view(work, dataset, cases)
    (work / "skipped.json").write_text(json.dumps(skipped))
    cmd = [python, str(RCAEVAL / "main.py"), "--method", method, "--dataset", dataset]
    if test:
        cmd.append("--test")
    t0 = time.time()
    with open(work / "main.log", "w") as log:
        rc = subprocess.run(cmd, cwd=work, stdout=log, stderr=subprocess.STDOUT).returncode
    n = len(list((work / "output" / "results").glob("*.json"))) if (work / "output" / "results").exists() else 0
    rec = {"method": method, "dataset": dataset, "returncode": rc, "seconds": round(time.time() - t0, 1),
           "result_files": n, "skipped_folders": skipped, "test": test}
    (work / "run.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec), flush=True)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="+", required=True)
    ap.add_argument("--datasets", nargs="+", required=True, choices=sorted(TARGET))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--test", action="store_true", help="main.py --test: first 2 cases only")
    ap.add_argument("--python", default=sys.executable, help="interpreter (RCD needs a Python 3.8 env)")
    ap.add_argument("--cases", help="CSV with a case_id column: run only these cases (e.g. data/test_waves.csv rows)")
    ap.add_argument("--waves", nargs="+", type=int, help="with --cases pointing at test_waves.csv: keep these waves")
    ap.add_argument("--tag", default="", help="output folder under runs/rcaeval/ (default: all)")
    args = ap.parse_args()
    cases = None
    if args.cases:
        import pandas as pd

        c = pd.read_csv(args.cases)
        if args.waves:
            c = c[c["wave"].isin(args.waves)]
        cases = set(c["case_id"])
    jobs = [(m, d) for m in args.methods for d in args.datasets]
    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(lambda j: run_one(j[0], j[1], args.test, args.python, cases, args.tag), jobs))


if __name__ == "__main__":
    main()

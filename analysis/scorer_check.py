"""Phase 0: confirm RCAEval's scorer runs end to end, and that rca.scoring reproduces it.

Runs RCAEval's own `main.py` (methods `dummy` = random ranking, and `baro`) on one
dataset, parses the per-fault Avg@5 it prints, then re-scores the same result files
with rca.scoring and compares. Writes results/scorer_check.csv.

Usage: python analysis/scorer_check.py --rcaeval ~/src/RCAEval --dataset re2-ob
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RAW_DIR, RESULTS_DIR  # noqa: E402
from rca.scoring import score_cases  # noqa: E402

DS_DIRS = {"re2-ob": ("RE2", "RE2-OB"), "re2-tt": ("RE2", "RE2-TT"), "re2-ss": ("RE2", "RE2-SS"),
           "re3-ob": ("RE3", "RE3-OB")}
FAULT_LABEL = {"cpu": "CPU", "mem": "MEM", "disk": "DISK", "socket": "SOCKET", "delay": "DELAY", "loss": "LOSS"}


def run_main(rcaeval: Path, workdir: Path, method: str, dataset: str) -> str:
    out = workdir / "output"
    if out.exists():
        shutil.rmtree(out)
    env = dict(os.environ, PYTHONHASHSEED="0")
    cmd = [sys.executable, str(rcaeval / "main.py"), "--method", method, "--dataset", dataset, "--length", "20"]
    res = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[-3000:])
    return res.stdout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rcaeval", type=Path, required=True)
    ap.add_argument("--dataset", default="re2-ob")
    ap.add_argument("--workdir", type=Path, default=Path.home() / "rcaeval-work")
    args = ap.parse_args()

    suite, folder = DS_DIRS[args.dataset]
    (args.workdir / "data" / suite).mkdir(parents=True, exist_ok=True)
    link = args.workdir / "data" / suite / folder
    if not link.exists():
        link.symlink_to(RAW_DIR / folder)

    rows = []
    for method in ["dummy", "baro"]:
        stdout = run_main(args.rcaeval, args.workdir, method, args.dataset)
        printed = {m.group(1): float(m.group(2)) for m in re.finditer(r"Avg@5-(\w+):\s+([\d.]+)", stdout)}
        cases = []
        for rp in glob.glob(str(args.workdir / "output" / "results" / "*.json")):
            service, fault = Path(rp).name.split("_")[:2]
            data = json.load(open(rp))
            if "error" in data:
                continue
            cases.append({"ranked": data["0"], "gt_service": service, "fault": fault, "dataset": folder})
        for fault, label in FAULT_LABEL.items():
            sub = [c for c in cases if c["fault"] == fault]
            if not sub:
                continue
            ours = score_cases(sub, "service")
            rows.append({"method": method, "dataset": folder, "fault": fault, "n": ours["n"],
                         "main_py_avg5": printed.get(label), "ours_avg5": round(ours["Avg@5"], 2),
                         "ours_ac1": round(ours["AC@1"], 4), "match": printed.get(label) == round(ours["Avg@5"], 2)})
        allc = score_cases(cases, "service")
        rows.append({"method": method, "dataset": folder, "fault": "all", "n": allc["n"], "main_py_avg5": None,
                     "ours_avg5": round(allc["Avg@5"], 4), "ours_ac1": round(allc["AC@1"], 4), "match": None})
        print(stdout[-600:])
    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_DIR / "scorer_check.csv", index=False)
    print(df.to_string())


if __name__ == "__main__":
    main()

"""Remaining Part 1 test runs on the frozen system (approved by the user 2026-10-31), one stage after another.

Stages, in order:
  test_r1     waves 3 and 4 (data/test_wave3.csv, data/test_wave4.csv): run 1 on the second half of the test set
  test_detect RE2 test cases with --fault-time detect (SPEC 9.1, onset-detection run)
  test_r2     all 676 test cases, run 2
  test_r3     all 676 test cases, run 3
Each stage runs `python -m rca.run` from the frozen worktree (part1-frozen-v2), cases split between the two Google
Cloud projects, WORKERS cases at a time per project. rca.run skips cases that already have a result, so the script
can be restarted at any time. A marker ~/<run_id>[_<tag>].done records a finished stage.

Usage (on the server): nohup python scripts/test_runs.py [--only test_r1 ...] [--workers 3] > ~/test_runs.log 2>&1 &
"""
from __future__ import annotations

import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

HOME = Path.home()
FROZEN = HOME / "deeprca-frozen"
REPO = HOME / "deeprca"
PY = str(HOME / "miniconda3" / "envs" / "deeprca" / "bin" / "python")
PROJECTS = ["mtp1-512709", "project-53e716a1-3b76-4d08-9bf"]
SPLITS = HOME / "test_splits"
DATA = REPO / "data"


def cases(stage: str) -> list[str]:
    if stage == "test_r1":
        return [c for w in (3, 4) for c in pd.read_csv(DATA / f"test_wave{w}.csv")["case_id"]]
    waves = pd.read_csv(DATA / "test_waves.csv")
    if stage == "test_detect":
        return list(waves.loc[waves["dataset"].str.startswith("RE2"), "case_id"])
    return list(waves["case_id"])


STAGES = {"test_r1": [], "test_detect": ["--fault-time", "detect"], "test_r2": [], "test_r3": []}


def run(cmd: list[str], project: str, log: Path) -> int:
    env = {**os.environ, "DEEPRCA_GCP_PROJECT": project}
    with open(log, "a") as f:
        return subprocess.run(cmd, cwd=FROZEN, env=env, stdout=f, stderr=subprocess.STDOUT).returncode


def stage(name: str, workers: int) -> None:
    done = HOME / f"{name}.done"
    if done.exists():
        print(f"{name}: already done", flush=True)
        return
    ids = cases(name)
    SPLITS.mkdir(exist_ok=True)
    jobs = []
    for i, proj in enumerate(PROJECTS):
        part = SPLITS / f"{name}_{i}.csv"
        pd.DataFrame({"case_id": ids[i::len(PROJECTS)]}).to_csv(part, index=False)
        jobs.append(([PY, "-m", "rca.run", "--cases", str(part), "--run-id", name, "--workers", str(workers),
                      *STAGES[name]], proj))
    print(f"{name}: {len(ids)} cases, {workers} at a time per project", flush=True)
    with ThreadPoolExecutor(len(jobs)) as ex:
        codes = list(ex.map(lambda j: run(j[0], j[1], HOME / f"{name}_{j[1][:4]}.log"), jobs))
    print(f"{name}: exit codes {codes}", flush=True)
    if all(c == 0 for c in codes):
        done.touch()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=list(STAGES))
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    for name in STAGES:
        if name in args.only:
            stage(name, args.workers)


if __name__ == "__main__":
    main()

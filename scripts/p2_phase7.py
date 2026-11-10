"""Run the Part 2 Phase 7 experiments on the frozen system, one after another (Option A, 2026-10-28).

Each experiment runs `python -m rca.run` from the frozen worktree (FROZEN, part1-frozen-v2) with its variant
switches, cases split between the two Google Cloud projects (2 cases at a time each). Planted-lead runs (A2) need
one injection file per case, so each case is its own rca.run call. Every run id is p2_<name>; rca.run skips cases
that already have a result, so the script can be restarted. A marker file ~/p2_<name>.done records completion.

Usage (on the server): python scripts/p2_phase7.py [--only p2_nocritic ...]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

HOME = Path.home()
FROZEN = HOME / "deeprca-frozen"
REPO = HOME / "deeprca"
PY = str(HOME / "miniconda3" / "envs" / "deeprca" / "bin" / "python")
PROJECTS = ["mtp1-512709", "project-53e716a1-3b76-4d08-9bf"]
SPLITS = HOME / "p2_splits"

SAMPLE = REPO / "data" / "p2_sample.csv"
A2 = REPO / "data" / "p2_a2_cases.csv"
C3 = REPO / "data" / "p2_c3_cases.csv"
INJ = REPO / "data" / "p2_injections"

D1 = REPO / "data" / "p2_d1_cases.csv"

# Order (changed 2026-10-28 at the user's request): the experiments that match the OmniRCA analysis first
# (A2 planted leads, C3.2 hidden names, D1 stability re-run, model comparison), then the ablation ladder.
EXPERIMENTS = [
    ("p2_a2_plausible_fake_flagged_span", A2, ["INJ"]),
    ("p2_a2_implausible_fake_flagged_span", A2, ["INJ"]),
    ("p2_a2_plausible_wrong_candidate_rank", A2, ["INJ"]),
    ("p2_a2_implausible_wrong_candidate_rank", A2, ["INJ"]),
    ("p2_anon", C3, ["--anonymize", "on"]),
    ("p2_rerun", D1, []),
    ("p2_mini", SAMPLE, ["--model", "small"]),
    ("p2_nocritic", SAMPLE, ["--critic", "off"]),
    ("p2_noguard", SAMPLE, ["--guardrail", "off"]),
    ("p2_single", SAMPLE, ["--mode", "single_agent"]),
    ("p2_codeloop", SAMPLE, ["--mode", "code_loop"]),
    ("p2_notraces", C3, ["--traces", "off"]),
]


def run(cmd: list[str], project: str, log: Path) -> int:
    env = {**os.environ, "DEEPRCA_GCP_PROJECT": project}
    with open(log, "a") as f:
        return subprocess.run(cmd, cwd=FROZEN, env=env, stdout=f, stderr=subprocess.STDOUT).returncode


def plain(name: str, cases: Path, flags: list[str]) -> None:
    ids = list(pd.read_csv(cases)["case_id"])
    SPLITS.mkdir(exist_ok=True)
    jobs = []
    for i, proj in enumerate(PROJECTS):
        part = SPLITS / f"{name}_{i}.csv"
        pd.DataFrame({"case_id": ids[i::2]}).to_csv(part, index=False)
        jobs.append(([PY, "-m", "rca.run", "--cases", str(part), "--run-id", name, "--workers", "2", *flags], proj))
    with ThreadPoolExecutor(2) as ex:
        list(ex.map(lambda j: run(j[0], j[1], HOME / f"{name}_{j[1][:4]}.log"), jobs))


def injected(name: str, cases: Path) -> None:
    folder = INJ / name.replace("p2_a2_", "")
    ids = list(pd.read_csv(cases)["case_id"])
    jobs = [([PY, "-m", "rca.run", "--cases", c, "--run-id", name, "--workers", "1", "--injection", str(folder / f"{c}.json")],
             PROJECTS[i % 2]) for i, c in enumerate(ids)]
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda j: run(j[0], j[1], HOME / f"{name}.log"), jobs))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    for name, cases, flags in EXPERIMENTS:
        if args.only and name not in args.only:
            continue
        marker = HOME / f"{name}.done"
        if marker.exists():
            continue
        t0 = time.time()
        print(f"{time.strftime('%H:%M:%S')} start {name}", flush=True)
        if flags == ["INJ"]:
            injected(name, cases)
        else:
            plain(name, cases, flags)
        marker.write_text(f"{round(time.time() - t0)} s\n")
        print(f"{time.strftime('%H:%M:%S')} done {name} in {round((time.time() - t0) / 60)} min", flush=True)


if __name__ == "__main__":
    sys.exit(main())

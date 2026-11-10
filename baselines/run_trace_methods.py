"""Run RCAEval's trace-based baselines that its main.py cannot drive (Part 2, Phase 6 step 2).

RCAEval main.py (commit 2fca61b) hands every method the metrics table, but `tracerca` and `microrank` expect the
span table (traces.csv: traceID, spanID, serviceName, methodName, operationName, startTime in microseconds,
duration). Their own code shows the intended call (commented line `pd.read_csv(".../traces.csv")` and an injection
time in microseconds), so here each is called through the library function exactly that way, unchanged.

`pdiagnose` exists only as a demo `main()` with hard-coded paths and no return value. Its body is reproduced below
with the paths made parameters and the ranking returned instead of printed; nothing else is changed (including its
use of all log lines, not just the window, and its "frontendservice" -> "frontend" rename).

Output mirrors main.py: runs/rcaeval/<tag>/<method>/<dataset>/output/results/<service>_<fault>_<rep>.json = {"0": ranks},
or <...>_failed.json = {"error": ...}. Only cases with traces are run.

Usage: python baselines/run_trace_methods.py --methods tracerca microrank pdiagnose --datasets re2-ob re2-tt
       --cases data/test_waves.csv --waves 1 2 --tag w12 [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import warnings
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rca.adapter.layout import case_id_for, list_raw_cases  # noqa: E402
from rca.paths import RAW_DIR, RUNS_DIR  # noqa: E402


def pdiagnose_case(case_dir: Path) -> list[str]:
    """RCAEval/e2e/pdiagnose.py main(), with its file paths as parameters and the ranking returned."""
    from RCAEval.e2e.pdiagnose import get_operation_slo

    ALPHA = 5
    metric_df = pd.read_csv(case_dir / "simple_metrics.csv")
    log_df = pd.read_csv(case_dir / "logs.csv")
    span_df = pd.read_csv(case_dir / "traces.csv")
    span_df["methodName"] = span_df["methodName"].fillna(span_df["operationName"])
    span_df["operation"] = span_df["serviceName"] + "_" + span_df["methodName"]
    inject_time = int(open(case_dir / "inject_time.txt").readline())

    normal_metric_df = metric_df[metric_df["time"] < inject_time]
    metric_slo = {m: [normal_metric_df[m].mean(), normal_metric_df[m].std()] for m in normal_metric_df.columns if "time" not in m}
    metric_q = {m: 0 for m in normal_metric_df.columns if "time" not in m}
    anomal_metric_df = metric_df[metric_df["time"] >= inject_time]
    for m in metric_q.keys():
        metric_q[m] = len(anomal_metric_df[anomal_metric_df[m] >= metric_slo[m][0] + 3 * metric_slo[m][1]])
    service_dict = {k.split("_")[0]: 0 for k in metric_q.keys()}
    for k, v in metric_q.items():
        s, m = k.split("_")
        service_dict[s] += ALPHA * v

    inject_time_log = inject_time * 1_000_000
    log_q = {c: 0 for c in log_df["container_name"].unique()}
    for c in log_q.keys():
        log_q[c] = len(log_df[(log_df["container_name"] == c) & (log_df["message"].str.contains("error|fail"))])
    for k, v in log_q.items():
        service_dict[k] += ALPHA * v

    normal_span_df = span_df[span_df["startTime"] + span_df["duration"] < inject_time_log]
    anomal_span_df = span_df[span_df["startTime"] + span_df["duration"] >= inject_time_log].copy()
    normal_slo = get_operation_slo(normal_span_df)
    anomal_span_df["mean"] = anomal_span_df["operation"].apply(lambda op: normal_slo[op]["mean"])
    anomal_span_df["std"] = anomal_span_df["operation"].apply(lambda op: normal_slo[op]["std"])
    anomal_span_df["abnormal"] = anomal_span_df["duration"] / 1_000 >= anomal_span_df["mean"] + 3 * anomal_span_df["std"]
    trace_q = {k: 0 for k in anomal_span_df.serviceName.unique()}
    for s in trace_q.keys():
        score = int(anomal_span_df[anomal_span_df["serviceName"] == s].abnormal.sum())
        if s == "frontendservice":
            s = "frontend"
        service_dict[s] += ALPHA * score
    rank_list = [(k, v) for k, v in service_dict.items()]
    rank_list.sort(key=lambda x: x[1], reverse=True)
    return [k for k, _ in rank_list]


def library_case(method: str, case_dir: Path) -> list[str]:
    from RCAEval import e2e

    spans = pd.read_csv(case_dir / "traces.csv")
    inject_us = int(open(case_dir / "inject_time.txt").readline()) * 1_000_000
    return getattr(e2e, method)(spans, inject_time=inject_us, dataset=None)["ranks"]


def one(job) -> dict:
    method, dataset, case_dir, out_dir = job
    case_dir = Path(case_dir)
    stem = f"{case_dir.parent.name}_{case_dir.name}"
    t0 = time.time()
    try:
        ranks = pdiagnose_case(case_dir) if method == "pdiagnose" else library_case(method, case_dir)
        (Path(out_dir) / f"{stem}.json").write_text(json.dumps({"0": list(map(str, ranks))}))
        ok = True
    except Exception as e:  # recorded, not hidden
        (Path(out_dir) / f"{stem}_failed.json").write_text(json.dumps({"error": f"{type(e).__name__}: {e}",
                                                                           "trace": traceback.format_exc()[-1500:]}))
        ok = False
    return {"method": method, "dataset": dataset, "case": stem, "ok": ok, "seconds": round(time.time() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="+", required=True, choices=["tracerca", "microrank", "pdiagnose"])
    ap.add_argument("--datasets", nargs="+", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--waves", nargs="+", type=int)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    c = pd.read_csv(args.cases)
    if args.waves:
        c = c[c["wave"].isin(args.waves)]
    keep = set(c["case_id"])
    jobs = []
    for m in args.methods:
        for d in args.datasets:
            out = RUNS_DIR / "rcaeval" / args.tag / m / d / "output" / "results"
            out.mkdir(parents=True, exist_ok=True)
            cases, _ = list_raw_cases(d.upper())
            for cd in cases:
                if case_id_for(d.upper(), cd) in keep and (cd / "traces.csv").exists():
                    if not any(out.glob(f"{cd.parent.name}_{cd.name}*.json")):
                        jobs.append((m, d, str(cd), str(out)))
    print(f"{len(jobs)} jobs", flush=True)
    if args.workers <= 1:
        # one case at a time in this process: the least memory, and nothing to hang (WORKLOG 2026-10-28)
        for j in jobs:
            print(json.dumps(one(j)), flush=True)
        return
    # spawn, not fork: forked workers deadlocked (0% CPU) under the threads pandas starts (WORKLOG 2026-10-28)
    with ProcessPoolExecutor(args.workers, max_tasks_per_child=4, mp_context=mp.get_context("spawn")) as ex:
        for r in ex.map(one, jobs):
            print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()

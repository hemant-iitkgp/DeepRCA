"""Run the system on a case set.

  python -m rca.run --cases dev --run-id dev1 [--datasets RE2-OB ...] [--limit N] [--workers 4]
                    [--mode full|single_agent|code_loop] [--guardrail on|off] [--critic on|off] [--model primary]
                    [--injection path.json] [--anonymize on|off] [--fault-time provided|detect] [--traces on|off]

--cases: dev | test | all | comma-separated case ids | path to a CSV with a case_id column.
Writes runs/<run_id>/<case_id>/result.json per case, runs/<run_id>/results.jsonl, and a manifest in
manifests/<run_id>.json (config, variant, git commit).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from rca.paths import ROOT, RUNS_DIR, SPLITS_CSV, load_env, models_config, system_config


def select_cases(spec: str, datasets: list[str] | None, limit: int | None) -> pd.DataFrame:
    sp = pd.read_csv(SPLITS_CSV)
    if spec in ("dev", "test"):
        sp = sp[sp["split"] == spec]
    elif spec == "all":
        pass
    elif Path(spec).exists():
        ids = set(pd.read_csv(spec)["case_id"])
        sp = sp[sp["case_id"].isin(ids)]
    else:
        sp = sp[sp["case_id"].isin(set(spec.split(",")))]
    if datasets:
        sp = sp[sp["dataset"].isin(datasets)]
    sp = sp.sort_values(["dataset", "case_id"])
    return sp.head(limit) if limit else sp


def _one(args):
    ds, cid, run_id, variant = args
    load_env()
    from rca.agent.runner import run_case

    try:
        return run_case(ds, cid, run_id, variant)
    except Exception:
        return {"dataset": ds, "case_id": cid, "run_id": run_id, "status": "crash_outer", "error": traceback.format_exc()[-3000:]}


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--datasets", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    for k in ("mode", "guardrail", "critic", "model", "injection", "anonymize", "fault-time", "traces"):
        ap.add_argument(f"--{k}")
    args = ap.parse_args()
    load_env()

    variant = {k.replace("-", "_"): getattr(args, k.replace("-", "_")) for k in
               ("mode", "guardrail", "critic", "model", "injection", "anonymize", "fault-time", "traces")
               if getattr(args, k.replace("-", "_")) is not None}
    cases = select_cases(args.cases, args.datasets, args.limit)
    run_dir = RUNS_DIR / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (ROOT / "manifests").mkdir(exist_ok=True)
    manifest = {"run_id": args.run_id, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "git_commit": git_commit(),
                "cases": args.cases, "datasets": args.datasets, "n_cases": len(cases), "variant_overrides": variant,
                "system_config": system_config(), "models": models_config()}
    (ROOT / "manifests" / f"{args.run_id}.json").write_text(json.dumps(manifest, indent=1, default=str))

    jobs = [(r.dataset, r.case_id, args.run_id, variant) for r in cases.itertuples()]
    t0 = time.time()
    state = {"done": 0, "total": len(jobs), "stopped": False}
    for attempt in range(4):  # first pass, then up to 3 passes for cases throttled by the provider
        retry = _pass(jobs, args.workers, run_dir, state, t0)
        if state["stopped"] or not retry:
            break
        print(f"{len(retry)} throttled cases; waiting before pass {attempt + 2}", flush=True)
        time.sleep(120 * (attempt + 1))
        jobs = retry
    else:
        print(f"{len(retry)} cases still throttled; rerun the same command later to finish them", flush=True)


def _pass(jobs, workers, run_dir, state, t0) -> list:
    retry: list = []
    # one fresh process per case: the OpenAI async client is bound to the event loop that created it
    with ProcessPoolExecutor(workers, max_tasks_per_child=1) as ex, open(run_dir / "results.jsonl", "a") as out:
        futs = [ex.submit(_one, j) for j in jobs]
        for f in as_completed(futs):
            r = f.result()
            if r.get("status") == "billing_stop":
                # the billed project is out of credit: stop the whole run; finished cases are kept and a rerun of
                # the same command (after switching DEEPRCA_GCP_PROJECT) continues with the unfinished ones
                print(f"BILLING STOP on {r.get('case_id')}: {str(r.get('error'))[-200:]}", flush=True)
                for g in futs:
                    g.cancel()
                ex.shutdown(wait=True, cancel_futures=True)
                print("Run stopped. Switch the project (DEEPRCA_GCP_PROJECT) and rerun the same command to resume.", flush=True)
                state["stopped"] = True
                return []
            if r.get("status") == "quota_retry":
                retry.append((r["dataset"], r["case_id"], r["run_id"], jobs[0][3]))
                print(f"quota throttled, will redo: {r.get('case_id')}", flush=True)
                continue
            state["done"] += 1
            out.write(json.dumps(r, default=str) + "\n")
            out.flush()
            print(f"[{state['done']}/{state['total']}] {r.get('dataset')} {r.get('case_id')} status={r.get('status')} "
                  f"report={r.get('report_status')} top={(r.get('ranked_v3') or [None])[0]} "
                  f"cost=${r.get('cost_usd', 0):.4f} t={r.get('latency_s')}s elapsed={time.time() - t0:.0f}s", flush=True)
    return retry

if __name__ == "__main__":
    main()

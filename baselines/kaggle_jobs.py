"""Offload the slow RCAEval baselines (Train Ticket) to Kaggle CPU notebooks (Part 2 Phase 6; WORKLOG 2026-10-29).

On the shared institute server CIRCA and multi-source CIRCA need hours per Train Ticket case (RE2-TT about 200 hours
in total). Each Kaggle notebook runs the same unmodified RCAEval main.py (commit 2fca61b, Python 3.12) on its shard of
cases: it downloads the RCAEval zips from Zenodo record 14590730, extracts only the files main.py reads for those cases,
builds main.py's data layout, and runs one main.py per CPU core on a subset. Results are copied to /kaggle/working as
they appear, and the notebook stops itself before Kaggle's 12-hour limit so partial results are kept.

  (--prefix names one round of notebooks; --env rcd uses RCAEval's Python 3.8 RCD mode)
  prepare  build the job list (our waves 1-2 cases minus results already on the server) and one notebook per shard
  push     upload the notebooks (they start running)
  status   show each notebook's state
  fetch    download finished outputs into runs/rcaeval/w12/<method>/<dataset>/output/results/

Usage: python baselines/kaggle_jobs.py prepare --jobs circa:re1-tt circa:re2-tt circa:re3-tt mmcirca:re2-tt mmcirca:re3-tt --shards 5
       python baselines/kaggle_jobs.py push | status | fetch
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rca.adapter.layout import case_id_for, list_raw_cases  # noqa: E402
from rca.paths import DATA_DIR, RUNS_DIR  # noqa: E402

USER = "hemant159"
KDIR = Path.home() / "kaggle_kernels"
KAGGLE = str(Path(sys.executable).parent / "kaggle")
# DeepRCA's own Kaggle config (only USER's kaggle.json): ~/.kaggle is shared with another project on the same server
# login, whose login switch sent two notebooks to another account (WORKLOG 2026-10-29)
KCFG = Path.home() / ".kaggle_deeprca"
# kaggle>=2 reads ~/.kaggle/access_token before kaggle.json whatever KAGGLE_CONFIG_DIR says, and the other project left
# its own account's token there, so run the CLI with an empty HOME and no token variable (WORKLOG 2026-10-30)
KHOME = Path.home() / ".kaggle_deeprca_home"
KENV = {**{k: v for k, v in os.environ.items() if k != "KAGGLE_API_TOKEN"},
        "KAGGLE_CONFIG_DIR": str(KCFG), "HOME": str(KHOME)}
_checked = False


def kaggle(*args: str, **kw) -> subprocess.CompletedProcess:
    global _checked
    cfg = json.loads((KCFG / "kaggle.json").read_text())
    if cfg.get("username") != USER or len(list(KCFG.iterdir())) != 1:
        sys.exit(f"{KCFG} must hold only {USER}'s kaggle.json")
    if not _checked:  # the account the CLI actually authenticates as, not the one the file names
        KHOME.mkdir(exist_ok=True)
        if any(KHOME.iterdir()):
            sys.exit(f"{KHOME} must be empty")
        view = subprocess.run([KAGGLE, "config", "view"], env=KENV, capture_output=True, text=True).stdout
        if f"username: {USER}" not in view or "ACCESS_TOKEN" in view:
            sys.exit(f"Kaggle CLI does not authenticate as {USER} with kaggle.json; refusing")
        _checked = True
    return subprocess.run([KAGGLE, *args], env=KENV, **kw)
COMMIT = "2fca61b9730a69c21ef72411844735634dbb010f"

NOTEBOOK = r'''
import json, os, shutil, subprocess, sys, time, zipfile, urllib.request
from pathlib import Path
T0 = time.time(); LIMIT = 11 * 3600
JOBS = json.loads(%(jobs)r)
COMMIT = %(commit)r
TMP = Path("/kaggle/tmp"); OUT = Path("/kaggle/working/out"); TMP.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
TARGET = {"re1-tt": "data/train-ticket", "re2-tt": "data/RE2/RE2-TT", "re3-tt": "data/RE3/RE3-TT"}
NEED = {"data.csv", "simple_metrics.csv", "inject_time.txt", "logts.csv", "tracets_err.csv", "tracets_lat.csv"}
sh = lambda c: subprocess.run(c, shell=True, check=True)
sh("pip install -q uv")
sh(f"git clone -q https://github.com/phamquiluan/RCAEval.git {TMP}/RCAEval && cd {TMP}/RCAEval && git checkout -q {COMMIT}")
ENV = %(env)r
if ENV == "rcd":
    # RCAEval's RCD mode (docs/SETUP.md): Python 3.8 env at RCAEval/env-rcd, then script/link.sh. The packages are the
    # server env-rcd's exact versions (baselines/rcd_requirements.txt); tigramite and cairocffi import numpy / cffi in
    # their builds, so those go in first and the rest is built without isolation (tested on the server, WORKLOG 2026-10-29)
    E = f"{TMP}/RCAEval/env-rcd/bin/python"
    (TMP / "rcd_req.txt").write_text(%(rcd_req)r)
    sh(f"uv python install 3.8 && uv venv -q -p 3.8 {TMP}/RCAEval/env-rcd && uv pip install -q --python {E} wheel setuptools numpy==1.23.5 cffi==1.15.1"
       f" && uv pip install -q --python {E} --no-build-isolation -r {TMP}/rcd_req.txt && uv pip install -q --python {E} --no-deps -e {TMP}/RCAEval"
       f" && cd {TMP}/RCAEval && bash script/link.sh")
    PY = f"{TMP}/RCAEval/env-rcd/bin/python"
else:
    sh(f"uv python install 3.12 && uv venv -q -p 3.12 {TMP}/venv && uv pip install -q --python {TMP}/venv/bin/python -e '{TMP}/RCAEval[default]'")
    PY = f"{TMP}/venv/bin/python"
# data: only the files main.py reads, only for this shard's cases
for ds in sorted({j["dataset"] for j in JOBS}):
    name = ds.upper(); z = TMP / f"{name}.zip"
    urllib.request.urlretrieve(f"https://zenodo.org/records/14590730/files/{name}.zip?download=1", z)
    stems = {j["stem"] for j in JOBS if j["dataset"] == ds}
    with zipfile.ZipFile(z) as zf:
        for m in zf.namelist():
            p = m.split("/")
            if len(p) == 4 and p[3] in NEED and f"{p[1]}/{p[2]}" in stems:
                zf.extract(m, TMP / "raw")
    z.unlink()
# one main.py per core, each on its own subset of cases
ncpu = os.cpu_count() or 4
procs = []
groups = {}
for i, j in enumerate(JOBS):
    groups.setdefault((j["method"], j["dataset"]), []).append(j["stem"])
slots = []
for (m, ds), stems in groups.items():
    k = max(1, min(len(stems), round(ncpu * len(stems) / len(JOBS))))
    for w in range(k):
        slots.append((m, ds, stems[w::k]))
env = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
queue = list(slots)
def launch(m, ds, stems, idx):
    work = TMP / "work" / f"{m}_{ds}_{idx}"
    for s in stems:
        dst = work / TARGET[ds] / s
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            os.symlink(TMP / "raw" / ds.upper() / s, dst)
    log = open(work / "main.log", "w")
    return (m, ds, work, subprocess.Popen([PY, f"{TMP}/RCAEval/main.py", "--method", m, "--dataset", ds], cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT))
def sync():
    for m, ds, work, p in procs:
        res = work / "output" / "results"
        if res.exists():
            d = OUT / m / ds; d.mkdir(parents=True, exist_ok=True)
            for f in res.glob("*.json"):
                shutil.copy(f, d / f.name)
idx = 0
while queue or any(p.poll() is None for *_, p in procs):
    while queue and sum(p.poll() is None for *_, p in procs) < ncpu:
        m, ds, stems = queue.pop(0); procs.append(launch(m, ds, stems, idx)); idx += 1
    sync()
    if time.time() - T0 > LIMIT:
        for *_, p in procs:
            if p.poll() is None: p.kill()
        break
    time.sleep(60)
sync()
json.dump({"elapsed_s": round(time.time() - T0), "results": sum(1 for _ in OUT.rglob("*.json"))}, open("/kaggle/working/summary.json", "w"))
'''


def jobs_for(spec: list[str]) -> list[dict]:
    waves = pd.read_csv(DATA_DIR / "test_waves.csv")
    keep = set(waves[waves["wave"].isin([1, 2])]["case_id"])
    out = []
    for js in spec:
        method, ds = js.split(":")
        done_dir = RUNS_DIR / "rcaeval" / "w12" / method / ds / "output" / "results"
        done = {p.stem for p in done_dir.glob("*.json")} if done_dir.exists() else set()
        for cd in list_raw_cases(ds.upper())[0]:
            if case_id_for(ds.upper(), cd) not in keep or len(cd.parent.name.split("_")) != 2:
                continue
            if f"{cd.parent.name}_{cd.name}" in done:
                continue
            out.append({"method": method, "dataset": ds, "stem": f"{cd.parent.name}/{cd.name}"})
    return out


def prepare(spec: list[str], shards: int, prefix: str, env: str) -> None:
    jobs = jobs_for(spec)
    print(f"{len(jobs)} case-runs")
    for i in range(shards):
        part = jobs[i::shards]
        d = KDIR / f"{prefix}-{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "run.py").write_text(NOTEBOOK % {"jobs": json.dumps(part), "commit": COMMIT, "env": env,
                                                 "rcd_req": (ROOT / "baselines" / "rcd_requirements.txt").read_text()})
        (d / "kernel-metadata.json").write_text(json.dumps({
            "id": f"{USER}/{prefix}-{i}", "title": f"{prefix}-{i}", "code_file": "run.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": False, "enable_internet": True,
            "dataset_sources": [], "competition_sources": [], "kernel_sources": []}, indent=1))
        print(d.name, len(part), sorted({(j["method"], j["dataset"]) for j in part}))


def each(fn, prefix: str = "deeprca-bl", only: list[int] | None = None) -> None:
    for d in sorted(KDIR.glob(f"{prefix}-*")):
        if only is None or int(d.name.rsplit("-", 1)[1]) in only:
            fn(d)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "push", "status", "fetch"])
    ap.add_argument("--jobs", nargs="*")
    ap.add_argument("--shards", type=int, default=5)
    ap.add_argument("--prefix", default="deeprca-bl", help="notebook name prefix (one prefix per round)")
    ap.add_argument("--env", default="default", choices=["default", "rcd"], help="RCAEval mode: default (Py 3.12) or rcd (Py 3.8)")
    ap.add_argument("--only", nargs="*", type=int, help="shard numbers to act on (default: all of the prefix)")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.jobs, a.shards, a.prefix, a.env)
    elif a.cmd == "push":
        each(lambda d: kaggle("kernels", "push", "-p", str(d)), a.prefix, a.only)
    elif a.cmd == "status":
        each(lambda d: kaggle("kernels", "status", f"{USER}/{d.name}"), a.prefix, a.only)
    else:
        def fetch(d: Path) -> None:
            o = d / "output"
            o.mkdir(exist_ok=True)
            kaggle("kernels", "output", f"{USER}/{d.name}", "-p", str(o), capture_output=True)
            n = 0
            for f in (o / "out").rglob("*.json") if (o / "out").exists() else []:
                method, ds = f.parent.parent.name, f.parent.name
                dst = RUNS_DIR / "rcaeval" / "w12" / method / ds / "output" / "results" / f.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    dst.write_bytes(f.read_bytes())
                    n += 1
            print(d.name, "new results:", n)
        each(fetch, a.prefix, a.only)


if __name__ == "__main__":
    main()

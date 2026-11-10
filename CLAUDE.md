# CLAUDE.md

This project builds an agent-driven RCA system for microservices, tests it on the RCAEval benchmark, and then dissects and compares it using the OmniRCA analysis framework.

**Read `SPEC.md` in full before doing anything.** It is the source of truth for what to build, in what order, and how to evaluate it.

## Two parts, in order

- **Part 1: Build and test** (SPEC Phases 0 to 5). Build the system, run it on all 9 RCAEval datasets, write `reports/PART1_REPORT.md`, tag the code `part1-frozen`. Self-contained: no OmniRCA or RCLAgent runs, no baselines except the ported control and BARO inside `candidate_rank`.
- **Part 2: Diagnose and compare** (SPEC Phases 6 to 8). Baselines, RCLAgent, OmniRCA, ablations and the diagnostic framework, all on the frozen Part 1 system.
- **Part 3: Future work** (SPEC Section 15, proposed). Application, fixes, trained parts and generality tests, each as a new version. Only after Parts 1 and 2, and only with the user's approval per item.
- **Do not start Part 2 until the user has reviewed the Part 1 report and said to proceed.**

## Working rules

- Work phase by phase. Do not start a phase until the previous gate passes.
- Log every decision, deviation, failed attempt and finding in `WORKLOG.md`, dated, with the reason.
- Never write a number in any document unless a script in `analysis/` produced it into a CSV in `results/`; cite the CSV.
- Verify library APIs (deepagents, RCAEval, OpenAI) against the installed code before using them. Record the confirmed API in `WORKLOG.md`.
- Ground truth is read only by the scorer and analysis scripts. Tools and agents must never reach it.
- No service, system or dataset names in prompts, rules or tool logic.
- Tune only on the dev split. Freeze configuration before test runs and record the commit hash.
- Part 2 never modifies the frozen system; any fix is a new, separately reported version, and only with the user's agreement.
- Pinned models: GPT-4o (primary) and gpt-4o-mini (Part 2 ablation), temperature 0. See `config/models.yaml`.

## Stop and ask the user before

- Any run whose projected cost exceeds the approved budget (SPEC Sections 3.6 and 9.3).
- Changing the claims, the evaluation rules or the splits.
- Dropping or reordering a phase.
- Starting Part 2.
- Continuing past any condition in SPEC Section 13.

## Commands

Fill in as they are created:

Everything runs on the server (`ssh rcasrv`, repo at `~/deeprca`, env `~/miniconda3/envs/deeprca/bin/python`); `data/raw`, `data/canonical`, `data/cache` and `runs` are symlinks into `~/deeprca-data` and `~/deeprca-runs`. Edit locally, `git push srv main`, then `git pull` on the server; commit generated `results/` on the server and pull them locally. Do not pull on the server while a run is in progress (each case starts a fresh process that loads code from disk).

- Install: conda env with Python 3.12; `pip install -e ~/src/RCAEval[default]` (commit 2fca61b), then `pip install -r requirements.lock`
- Download data: Zenodo record 14590730 zips into `data/raw/zips`, md5-checked, unzipped into `data/raw/<dataset>/`
- Audit: `python analysis/audit_data.py`; scorer check: `python analysis/scorer_check.py --rcaeval ~/src/RCAEval --dataset re2-ob`
- Convert data: `python -m rca.adapter --workers 10`; topology: `python -m rca.adapter.topology`; splits (once only): `python -m rca.adapter.splits`
- Control: `python analysis/run_control.py`; code-only ceiling: `python analysis/code_ceiling.py --split dev`
- Run the system: `python -m rca.run --cases dev --run-id <id> --workers 8 [--mode ...] [--guardrail off] [--critic off] [--injection f.json] [--anonymize on] [--fault-time detect] [--traces off]`
- Score a run: `python analysis/eval_run.py --runs <id> --tag <id>`; dev tuning: `python analysis/tune_gate.py --runs <ids>`, `python analysis/fit_confidence.py --runs <ids>`
- Part 1 tables: `python analysis/part1_tables.py --runs <test runs> --onset <onset run>`
- Variant smoke tests: `bash scripts/smoke_variants.sh <tag>`
- Tests: `pytest` (adapter, isolation, tools, guardrails, scoring/gate)

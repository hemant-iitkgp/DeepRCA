# DeepRCA: agent-driven recursive root-cause analysis for microservices

A `deepagents`-based RCA system, tested on the nine RCAEval datasets.
- Deterministic code tools turn telemetry into evidence.
- Span-investigator sub-agents examine flagged spans in parallel.
- A main agent plans, tests hypotheses and consults a critic.
- Code guardrails decide what must be covered, and reject reports that skip work or blame a service without positive evidence.

`SPEC.md` is the source of truth. `WORKLOG.md` records every decision, deviation and failed attempt. Results are in `results/` (CSV files written by `analysis/` scripts), and reports are in `reports/`. This README contains no result numbers; every number is in a report that cites its CSV.

## Layout

- `rca/adapter/`: RCAEval to canonical Parquet (one folder per case, opaque case IDs), static topology, splits
- `rca/tools/`: code tools (`select_traces`, `trace_tree`, `metric_anomalies`, `log_anomalies`, `topology`, `fault_indicators`, `candidate_rank`, onset detection)
- `rca/control/`: the z-score control
- `rca/guardrails/`: `submit_report` checks, the gate (V4), confidence
- `rca/agent/`: main agent, sub-agents, prompts (`prompts/*_v1.md`), run state, transcript and provenance logging, runner
- `rca/run.py`: run any case set with any variant switch
- `rca/truth.py`, `rca/scoring.py`: ground truth and RCAEval scoring, used only by `analysis/`
- `config/system.yaml`: every tunable setting; `config/models.yaml`: pinned model

## Reproduce

1. Create a Python 3.12 environment. Install RCAEval (commit `2fca61b`) with `pip install -e RCAEval[default]`, then `pip install -r requirements.lock`.
2. Download the nine Zenodo zips (record 14590730) into `data/raw/zips/`, check their md5, and unzip into `data/raw/`.
3. Put `OPENAI_API_KEY=...` in `.env` (git-ignored).
4. Run, in order:
   ```
   python analysis/audit_data.py
   python analysis/scorer_check.py --rcaeval <path to RCAEval> --dataset re2-ob
   python -m rca.adapter --workers 10
   python -m rca.adapter.topology
   python analysis/run_control.py
   python analysis/code_ceiling.py --split dev
   python -m rca.run --cases dev --run-id dev --workers 8
   python analysis/eval_run.py --runs dev --tag dev
   ```
   `data/splits.csv` is committed and must not be regenerated.
5. Test runs and the Part 1 tables: see `CLAUDE.md` (Commands) and `reports/PART1_REPORT.md`.

## Model

The SPEC's primary model is GPT-4o. The available API project has access only to `gpt-4o-mini`, so the primary model is `gpt-4o-mini` (snapshot `gpt-4o-mini-2024-07-18`, checked on every response), at temperature 0 with seed 7. Switching models is one line in `config/models.yaml`; it requires re-tuning on dev and rerunning (see `WORKLOG.md`).

#!/bin/bash
# Model pilot round 2 (dev only): Gemini 3.1 Pro preview lost capacity on the shared pool (429 on every request),
# so Gemini 4 Argon and Gemini 3.7 Flash (the pre-declared fallback) are compared, in parallel.
PY=~/miniconda3/envs/deeprca/bin/python
run() { $PY -m rca.run --cases dev --run-id "pilot_$1" --workers 3 --model "$1" > ~/pilot_$1.log 2>&1; $PY analysis/eval_run.py --runs "pilot_$1" --tag "pilot_$1" > ~/pilot_$1_eval.log 2>&1; }
run argon & run fallback & wait
echo PILOT2_DONE > ~/pilot2_done.flag

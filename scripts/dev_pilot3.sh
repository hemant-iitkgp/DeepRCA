#!/bin/bash
# Pilot resumed on project mtp1-512709 (project1-446502 lost billing). Each run resumes: finished cases are kept.
PY=~/miniconda3/envs/deeprca/bin/python
run() { $PY -m rca.run --cases dev --run-id "pilot_$1" --workers 3 --model "$1" > ~/pilot_$1.log 2>&1; $PY analysis/eval_run.py --runs "pilot_$1" --tag "pilot_$1" > ~/pilot_$1_eval.log 2>&1; }
run argon & run fallback & run primary & wait
echo PILOT3_DONE > ~/pilot3_done.flag

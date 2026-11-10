#!/bin/bash
# Model pilot on the dev split (SPEC 3.2: tuning only on dev): Gemini 3.1 Pro, low vs high thinking.
# Gemini 4 Argon was dropped from the pilot (4x slower per call, no published price; WORKLOG).
PY=~/miniconda3/envs/deeprca/bin/python
for cfg in primary primary_high; do
  $PY -m rca.run --cases dev --run-id "pilot_$cfg" --workers 3 --model "$cfg" > ~/pilot_$cfg.log 2>&1
  $PY analysis/eval_run.py --runs "pilot_$cfg" --tag "pilot_$cfg" > ~/pilot_${cfg}_eval.log 2>&1
done
echo PILOT_DONE > ~/pilot_done.flag

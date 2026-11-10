#!/bin/bash
# Phase 4 gate: smoke-test every variant switch (SPEC 7.11) on 3 dev cases.
# Usage (on the server, repo root): bash scripts/smoke_variants.sh <tag>
set -u
TAG=${1:-sv1}
PY=~/miniconda3/envs/deeprca/bin/python
CASES=c50e54490db,c038a3fc481,c0849215fce
run() { name=$1; shift; echo "== $name"; $PY -m rca.run --cases $CASES --run-id "smoke_${TAG}_$name" --workers 3 "$@" 2>&1 | tail -3; }
run single     --mode single_agent
run codeloop   --mode code_loop
run noguard    --guardrail off
run nocritic   --critic off
run model      --model primary
run inj_span   --injection manifests/injections/smoke_fake_flagged_span.json
run inj_rank   --injection manifests/injections/smoke_wrong_candidate_rank.json
run inj_hyp    --injection manifests/injections/smoke_false_hypothesis.json
run anon       --anonymize on
run detect     --fault-time detect
run notraces   --traces off
echo SMOKE_DONE

"""Ground-truth loader. Only the scorer and analysis scripts may import this module.

`tests/test_truth_isolation.py` checks that nothing under rca/tools, rca/agent,
rca/control or rca/guardrails imports it, and the canonical case reader refuses
to open truth.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from rca.paths import CANONICAL_DIR


def load_truth(dataset: str, case_id: str) -> dict:
    with open(Path(CANONICAL_DIR) / dataset / case_id / "truth.json", encoding="utf-8") as f:
        return json.load(f)

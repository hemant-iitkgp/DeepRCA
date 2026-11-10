"""Confidence from evidence, computed in code (SPEC 7.7), never from agent agreement.

Features: critic verdict, number of positive evidence types for the top-1, whether the top-1 has
evidence against, support margin top-1 vs top-2, coverage, and whether the gate applied. A logistic
model is fitted on the dev split only (analysis/fit_confidence.py -> config/confidence.json); until
then a fixed prior weighting is used and the report says so.
"""
from __future__ import annotations

import json
import math

from rca.paths import CONFIG_DIR

FEATURES = ["critic_pass", "n_pos_types", "top1_has_against", "support_margin", "coverage", "gate_applied"]
_PRIOR = {"intercept": -1.0, "critic_pass": 0.5, "n_pos_types": 0.6, "top1_has_against": -0.4,
          "support_margin": 0.4, "coverage": 0.5, "gate_applied": 0.3}


def load_model() -> tuple[dict, str]:
    p = CONFIG_DIR / "confidence.json"
    if p.exists():
        m = json.loads(p.read_text())
        return m["coef"], m.get("source", "dev-fit")
    return _PRIOR, "prior (not fitted)"


def predict(features: dict) -> tuple[float, str]:
    coef, src = load_model()
    z = coef.get("intercept", 0.0) + sum(coef.get(k, 0.0) * float(features.get(k, 0.0)) for k in FEATURES)
    return 1.0 / (1.0 + math.exp(-z)), src

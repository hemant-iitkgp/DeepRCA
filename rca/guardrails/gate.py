"""The gate (SPEC 7.8): produces the V4 ranking from the agent's V3 ranking and the control's statistics.

Gate condition: few anomalous services AND a large z margin between the control's top-1 and top-2
(thresholds tuned on the dev split only, in config/system.yaml `gate`). When it holds, the agent's
top-1 replaces the control's top-1 only with at least two independent positive evidence types and
a passing critic; otherwise the control's top-1 goes first and the agent's top-1 second.
"""
from __future__ import annotations


def gate_holds(n_anomalous: int, z_margin: float, max_anom: int | None, min_margin: float | None) -> bool:
    if max_anom is None or min_margin is None:
        return False
    return n_anomalous <= max_anom and z_margin >= min_margin


def apply_gate(v3: list[str], control: dict, top1_evidence_types: set[str], critic_pass: bool,
               max_anom: int | None, min_margin: float | None) -> tuple[list[str], str]:
    if not v3:
        return list(control["ranked"]), "no_agent_answer"
    if not gate_holds(control["n_anomalous"], control["z_margin"], max_anom, min_margin):
        return list(v3), "gate_not_held"
    c_top, a_top = control["ranked"][0], v3[0]
    if c_top == a_top:
        return list(v3), "gate_held_agree"
    if len(top1_evidence_types) >= 2 and critic_pass:
        return list(v3), "gate_held_agent_override"
    v4 = [c_top, a_top] + [s for s in v3[1:] if s != c_top]
    return v4, "gate_held_control_first"

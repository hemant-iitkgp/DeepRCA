from rca.guardrails.gate import apply_gate
from rca.scoring import hit_at, indicator_for, score_cases


def test_service_level_matches_hand_count():
    rows = [
        {"ranked": ["a_cpu", "b_mem", "c"], "gt_service": "a", "fault": "cpu", "dataset": "RE2-OB"},   # rank 1
        {"ranked": ["b", "a-db", "c"], "gt_service": "a", "fault": "mem", "dataset": "RE2-OB"},        # rank 2 (-db stripped)
        {"ranked": ["b", "c", "d", "e", "f"], "gt_service": "a", "fault": "cpu", "dataset": "RE2-OB"}, # miss
    ]
    s = score_cases(rows, "service")
    assert s["n"] == 3
    assert abs(s["AC@1"] - 1 / 3) < 1e-9
    assert abs(s["AC@3"] - 2 / 3) < 1e-9
    assert abs(s["Avg@5"] - (1 / 3 + 2 / 3 * 4) / 5) < 1e-9


def test_indicator_mapping():
    assert indicator_for("disk", "RE1-TT") == "latency"
    assert indicator_for("disk", "RE2-TT") == "diskio"
    assert indicator_for("delay", "RE2-OB") == "latency"
    assert indicator_for("f1", "RE3-OB") is None


def test_hit_at():
    assert hit_at(["x", "y_cpu"], "y", 2) and not hit_at(["x", "y_cpu"], "y", 1)


CONTROL = {"ranked": ["c1", "c2", "c3"], "n_anomalous": 2, "z_margin": 10.0}


def test_gate_not_tuned_never_holds():
    v4, path = apply_gate(["a", "b"], CONTROL, {"metric", "log"}, True, None, None)
    assert v4 == ["a", "b"] and path == "gate_not_held"


def test_gate_control_first_without_strong_evidence():
    v4, path = apply_gate(["a", "c1", "b"], CONTROL, {"metric"}, True, 3, 5.0)
    assert v4 == ["c1", "a", "b"] and path == "gate_held_control_first"


def test_gate_override_with_two_types_and_critic_pass():
    v4, path = apply_gate(["a", "b"], CONTROL, {"metric", "edge_gap"}, True, 3, 5.0)
    assert v4 == ["a", "b"] and path == "gate_held_agent_override"
    v4, path = apply_gate(["a", "b"], CONTROL, {"metric", "edge_gap"}, False, 3, 5.0)
    assert v4[0] == "c1"

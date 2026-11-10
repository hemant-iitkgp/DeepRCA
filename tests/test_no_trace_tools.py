"""Every agent tool returns text (never raises) on cases without traces and without logs.

Added after the first test wave crashed on RE1 cases: an agent called a trace tool on a case with no traces
and the exception ended the case. This test calls the code tools only (no LLM, no scoring).
"""
import json

import pandas as pd
import pytest

from rca.paths import CANONICAL_DIR, SPLITS_CSV, system_config

ARGS = {
    "select_traces": {}, "trace_tree": {"trace_id": "nonexistent"}, "anomalous_services": {}, "next_frontier": {},
    "candidate_rank": {}, "evidence_summary": {}, "path_to_symptom": {"service": "x"}, "recent_changes": {},
    "similar_incidents": {}, "read_draft": {}, "read_finding": {"work_item_id": "x"},
    "span_context": {"work_item_id": "x"},
}


def first_case(ds):
    sp = pd.read_csv(SPLITS_CSV)
    return next((c for c, d in zip(sp["case_id"], sp["dataset"]) if d == ds and (CANONICAL_DIR / d / c / "case.json").exists()), None)


@pytest.mark.parametrize("dataset,hide", [("RE1-OB", False), ("RE1-SS", False), ("RE2-SS", False), ("RE2-OB", True)])
def test_tools_never_raise_without_traces(dataset, hide, tmp_path):
    from rca.agent.state import RunState
    from rca.agent.tools import build_tools
    from rca.tools.data import CaseData

    cid = first_case(dataset)
    if cid is None:
        pytest.skip("not converted")
    cd = CaseData(dataset, cid, hide_traces=hide)
    assert not cd.case["has_traces"]
    st = RunState(cd, tmp_path, system_config()["limits"], dict(system_config()["variant"]))
    tools = build_tools(st)
    svc = cd.services[0]
    calls = dict(ARGS)
    calls.update({"metric_anomalies": {"entity": svc}, "log_anomalies": {"service": svc}, "topology": {"service": svc},
                  "fault_indicators": {"service": svc}})
    for name, args in calls.items():
        out = tools[name].invoke(args)
        assert isinstance(out, str), name
    for name in ("select_traces", "trace_tree"):
        assert "no traces" in json.loads(tools[name].invoke(ARGS[name]))["error"]
    assert getattr(st, "tool_errors", 0) == 0, "a tool raised instead of returning a message"


def test_a_raising_tool_becomes_a_message(tmp_path, monkeypatch):
    from rca.agent import tools as tmod
    from rca.agent.state import RunState
    from rca.tools.data import CaseData

    cid = first_case("RE2-OB")
    if cid is None:
        pytest.skip("not converted")
    st = RunState(CaseData("RE2-OB", cid), tmp_path, system_config()["limits"], dict(system_config()["variant"]))

    def boom(*a, **k):
        raise TypeError("simulated failure")

    monkeypatch.setattr(tmod.topology, "topology", boom)
    out = tmod.build_tools(st)["topology"].invoke({"service": "x"})
    assert "simulated failure" in json.loads(out)["error"]
    assert st.tool_errors == 1


def test_service_items_are_one_parallel_level(tmp_path):
    from rca.agent.state import RunState
    from rca.agent.tools import build_tools
    from rca.tools.data import CaseData

    cid = first_case("RE1-SS")
    if cid is None:
        pytest.skip("not converted")
    st = RunState(CaseData("RE1-SS", cid), tmp_path, system_config()["limits"], dict(system_config()["variant"]))
    listed = json.loads(build_tools(st)["anomalous_services"].invoke({}))["work_items"]
    frontier = st.next_frontier()
    assert len(frontier) == len(listed)  # every anomalous service is on the first frontier
    assert [f["id"] for f in frontier] == [w["id"] for w in listed]  # deepest-first order kept

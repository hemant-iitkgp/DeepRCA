"""Code tools on real RCAEval cases (SPEC 0: unit-test every tool on real cases before agents use it)."""
import json

import pytest

from rca.paths import CANONICAL_DIR

MAX_CHARS = 8000


def first_case(dataset):
    d = CANONICAL_DIR / dataset
    if not d.exists():
        return None
    for c in sorted(d.iterdir()):
        if (c / "case.json").exists():
            return c.name
    return None


def cd_for(dataset):
    from rca.tools.data import CaseData

    cid = first_case(dataset)
    if cid is None:
        pytest.skip(f"{dataset} not converted")
    return CaseData(dataset, cid)


@pytest.mark.parametrize("dataset", ["RE2-OB", "RE2-TT"])
def test_select_and_tree(dataset):
    from rca.tools.traces import select_traces, span_table, trace_tree

    cd = cd_for(dataset)
    st = span_table(cd)
    assert (st["own_ms"] >= 0).all()
    assert (st["own_ms"] <= st["duration_ms"] + 1e-6).all()
    sel = select_traces(cd, k=5)
    assert 1 <= len(sel) <= 5
    w0, w1 = cd.window()
    for t in sel:
        tree = trace_tree(cd, t["trace_id"])
        assert tree["n_spans"] >= 1
        assert len(json.dumps(tree["spans"], default=str)) < 4 * MAX_CHARS
        for f in tree["flagged"]:
            assert f["reasons"] and f["blamed_service"]


def test_unobserved_callee_inferred():
    from rca.tools.traces import span_table

    cd = cd_for("RE2-OB")
    st = span_table(cd)
    # some services report no spans of their own; calls to them must still be attributed
    traced = set(st["service"])
    inferred = set(st["callee"].dropna())
    assert inferred, "no unobserved callee inferred"
    assert inferred <= set(cd.services)
    assert inferred - traced, "expected callees that report no spans"


@pytest.mark.parametrize("dataset", ["RE2-OB", "RE2-SS", "RE1-OB"])
def test_metric_log_topology_faults(dataset):
    from rca.tools.faults import fault_indicators
    from rca.tools.logs import log_anomalies
    from rca.tools.metrics import metric_anomalies
    from rca.tools.topology import topology

    cd = cd_for(dataset)
    svc = cd.services[0]
    m = metric_anomalies(cd, svc)
    assert "resource_metrics" in m and len(json.dumps(m)) < MAX_CHARS
    for a in m["resource_metrics"] + m["latency_error_traffic_metrics"]:
        assert a["peak_z"] > 3 and len(a["curve10"]) <= 10
    if cd.case["has_logs"]:
        la = log_anomalies(cd, cd.logs["service"].iloc[0])
        assert "anomalous_templates" in la or "note" in la
    else:
        assert "error" in log_anomalies(cd, svc)
    t = topology(cd, svc)
    assert t["service"] == svc
    fi = fault_indicators(cd, svc)
    assert isinstance(fi["candidates"], list)


@pytest.mark.parametrize("dataset", ["RE2-OB", "RE1-SS"])
def test_control_and_candidate_rank(dataset):
    from rca.control.zscore import control_rank
    from rca.tools.rank import candidate_rank

    cd = cd_for(dataset)
    c = control_rank(cd)
    assert set(c["ranked"]) == set(cd.services)
    assert c["scores"] == sorted(c["scores"], reverse=True)
    cr = candidate_rank(cd)
    assert cr["baro"] and cr["control_zscore"]

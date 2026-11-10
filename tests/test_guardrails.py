"""submit_report checks (SPEC 7.6) and evidence writers on a real dev case, without any LLM."""
import json

import pandas as pd
import pytest

from rca.paths import CANONICAL_DIR, SPLITS_CSV, system_config


@pytest.fixture
def state(tmp_path):
    from rca.agent.state import RunState
    from rca.tools.data import CaseData

    sp = pd.read_csv(SPLITS_CSV)
    dev = sp[(sp["split"] == "dev") & (sp["dataset"] == "RE2-OB")]
    cid = next((c for c in dev["case_id"] if (CANONICAL_DIR / "RE2-OB" / c / "case.json").exists()), None)
    if cid is None:
        pytest.skip("no converted dev case")
    st = RunState(CaseData("RE2-OB", cid), tmp_path, system_config()["limits"], dict(system_config()["variant"]))
    return st


def report(services, path=None, **kw):
    return {"ranked_services": [{"service": s, "source": "evidence"} for s in services], "ranked_indicators": [],
            "fault_type": "unknown", "fault_indicator": "", "evidence_path": path or services[:1], "critic_response": [],
            **kw}


def test_rejects_uncovered_items_and_missing_critic(state):
    from rca.guardrails.submit import check_report

    state.items["x1"] = {"kind": "span", "id": "x1", "depth": 1, "service": state.cd.services[0],
                         "blamed_service": state.cd.services[0], "reasons": ["own_time"]}
    fails = check_report(state, report(state.cd.services[:5]))
    kinds = {f.split(":")[0] for f in fails}
    assert "COVERAGE" in kinds and "CRITIC" in kinds


def test_rejects_short_dup_unknown_ranking(state):
    from rca.guardrails.submit import check_report

    s = state.cd.services
    fails = check_report(state, report([s[0], s[0], "not-a-service"]))
    text = " ".join(fails)
    assert "at least" in text and "duplicate" in text and "not in this case" in text


def test_top1_needs_cited_and_verified_positive_evidence(state):
    from rca.agent.tools import save_finding
    from rca.guardrails.support import positive_evidence

    svc = state.cd.services[0]
    state.items["x1"] = {"kind": "span", "id": "x1", "depth": 1, "service": svc, "blamed_service": svc, "reasons": []}
    # a finding citing only "nothing anomalous upstream" style evidence gives no positive type
    msg = save_finding(state, {"span_id": "x1", "service": svc, "abnormal": True, "blame": "self",
                               "evidence_for": [{"type": "other", "detail": "nothing anomalous upstream"}],
                               "evidence_against": [], "checked_against": True, "confidence": 0.9})
    assert msg == "finding saved"
    assert positive_evidence(state, svc) == set()
    # findings are written once
    again = save_finding(state, {"span_id": "x1", "service": svc, "abnormal": False, "blame": "none",
                                 "evidence_for": [], "evidence_against": [], "checked_against": True, "confidence": 0.1})
    assert "already exists" in again
    assert json.loads(state.finding_path("x1").read_text())["blame"] == "self"


def test_finding_service_is_set_by_code(state):
    from rca.agent.tools import save_finding

    svc = state.cd.services[1]
    state.items["x2"] = {"kind": "span", "id": "x2", "depth": 1, "service": svc, "blamed_service": svc, "reasons": []}
    save_finding(state, {"span_id": "x2", "service": "something-else", "abnormal": False, "blame": "none",
                         "evidence_for": [], "evidence_against": [{"type": "metric", "detail": "checked, none"}],
                         "checked_against": True, "confidence": 0.2})
    assert json.loads(state.finding_path("x2").read_text())["service"] == svc


def test_candidate_rank_locked_until_frontier_empty(state):
    from rca.agent.tools import build_tools

    state.items["x3"] = {"kind": "span", "id": "x3", "depth": 1, "service": state.cd.services[0],
                         "blamed_service": state.cd.services[0], "reasons": ["own_time"]}
    out = build_tools(state)["candidate_rank"].invoke({})
    assert "locked" in out

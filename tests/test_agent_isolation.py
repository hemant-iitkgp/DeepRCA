"""Agents cannot write files or run commands, whatever the model provider (evidence is written only by code).

deepagents keeps every filesystem tool in the tool node and hides excluded ones from the model per provider
(harness profile), so the check is (1) the read-only profile resolves for each provider the system runs on, and
(2) every agent is built with the deny-all-writes filesystem permission.
"""
import pandas as pd
import pytest

FORBIDDEN = {"write_file", "edit_file", "delete", "execute", "glob", "grep"}


@pytest.mark.parametrize("model_key", ["primary", "small", "gpt4o_mini_dev"])
def test_read_only_profile_resolves(model_key, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from deepagents.profiles.harness.harness_profiles import _harness_profile_for_model

    from rca.agent import build
    from rca.paths import load_env, models_config

    load_env()
    try:
        llm = build.make_llm(models_config()["models"][model_key])
    except Exception as e:  # credentials not available on this machine
        pytest.skip(f"model not constructible here: {e}")
    prof = _harness_profile_for_model(llm, None)
    assert FORBIDDEN <= set(prof.excluded_tools)
    assert prof.general_purpose_subagent is not None and prof.general_purpose_subagent.enabled is False


def test_every_agent_built_with_no_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from rca.agent import build
    from rca.agent.state import RunState
    from rca.paths import CANONICAL_DIR, SPLITS_CSV, models_config, system_config
    from rca.tools.data import CaseData

    sp = pd.read_csv(SPLITS_CSV)
    cid = next((c for c, d in zip(sp["case_id"], sp["dataset"]) if d == "RE2-OB" and (CANONICAL_DIR / d / c / "case.json").exists()), None)
    if cid is None:
        pytest.skip("no converted case")
    calls = []
    real = build.create_deep_agent

    def spy(*a, **kw):
        calls.append(kw)
        return real(*a, **kw)

    monkeypatch.setattr(build, "create_deep_agent", spy)
    st = RunState(CaseData("RE2-OB", cid), tmp_path, system_config()["limits"], dict(system_config()["variant"]))
    llm = build.make_llm(models_config()["models"]["gpt4o_mini_dev"])
    build.build_main_agent(st, llm)
    assert len(calls) >= 4  # main + investigator + tester + critic
    for kw in calls:
        perms = kw.get("permissions") or []
        assert any(p.mode == "deny" and "write" in p.operations and "/**" in p.paths for p in perms), kw.get("name")

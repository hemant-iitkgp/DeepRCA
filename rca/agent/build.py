"""Build the deepagents main agent and its sub-agents for one case (SPEC 7.3, 7.4).

Confirmed against deepagents 0.7.26 (see WORKLOG): `create_deep_agent(model, tools, system_prompt=,
subagents=, backend=, name=)`; sub-agents are `CompiledSubAgent` dicts {name, description, runnable}
launched by the built-in `task` tool; declarative/compiled sub-agents get no `task` tool, so they
cannot launch sub-agents. Each sub-agent runnable is wrapped here so that code enforces the launch
limit and the parallel cap and records per-launch tokens and duration (SPEC 3.6, 7.10).
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from deepagents import (FilesystemPermission, GeneralPurposeSubagentProfile, HarnessProfile, create_deep_agent,
                        register_harness_profile)
from deepagents.backends.filesystem import FilesystemBackend
from langchain.agents.middleware import ModelCallLimitMiddleware, TodoListMiddleware, ToolCallLimitMiddleware
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.config import merge_configs

from rca.agent.llm import MalformedCallRetry
from rca.agent.state import RunState
from rca.agent.tools import (CRITIC_TOOLS, INVESTIGATOR_TOOLS, MAIN_TOOLS, TESTER_TOOLS, CriticIn, FindingIn, HypothesisIn,
                             build_tools, save_critic, save_finding, save_hypothesis)

PROMPTS = Path(__file__).parent / "prompts"
PROMPT_VERSION = "v1"

# Agents get read-only file tools (ls, read_file); evidence is written only through structured tools.
# The profile is per provider, so it is registered for every provider the system can run on (the first Gemini
# pilot ran without it: the profile was registered for "openai" only, see WORKLOG).
_READ_ONLY = HarnessProfile(
    excluded_tools=frozenset({"write_file", "edit_file", "delete", "execute", "glob", "grep"}),
    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
)
for _provider in ("openai", "google_genai", "google_vertexai", "google"):
    register_harness_profile(_provider, _READ_ONLY)
# second layer, independent of provider: every agent write to the virtual filesystem is denied
NO_WRITES = [FilesystemPermission(operations=["write"], paths=["/**"], mode="deny")]


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}_{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def make_llm(mcfg: dict):
    from rca.agent.llm import make_llm as _make

    return _make(mcfg)


class _Counter(BaseCallbackHandler):
    def __init__(self):
        self.prompt = 0
        self.completion = 0
        self.calls = 0

    def on_llm_end(self, response, **kwargs):
        msg = getattr(response.generations[0][0], "message", None)
        u = getattr(msg, "usage_metadata", None) or {}
        self.prompt += int(u.get("input_tokens", 0))
        self.completion += int(u.get("output_tokens", 0))
        self.calls += 1


def _record_structured(st: RunState, kind: str, desc: str, out: dict, rec: dict) -> dict:
    """Write a sub-agent's structured final answer to its evidence file (code owns the files) and
    hand the main agent a short confirmation plus the answer."""
    sr = out.get("structured_response")
    if sr is None:
        rec["status"] = "no_structured_answer"
        return {"messages": [AIMessage(content=f"{kind} returned no structured answer; nothing was recorded.")]}
    data = sr.model_dump() if hasattr(sr, "model_dump") else dict(sr)
    if kind == "span-investigator":
        item = next((iid for iid in sorted(st.items, key=len, reverse=True) if iid in desc), None)
        msg = save_finding(st, data, item_id=item)
    elif kind == "hypothesis-tester":
        msg = save_hypothesis(st, data)
    else:
        msg = save_critic(st, data)
    rec["recorded"] = msg[:200]
    body = json.dumps(data, default=str)[:3000]
    return {"messages": [AIMessage(content=f"{msg}\n{body}")]}


def _wrap_subagent(st: RunState, kind: str, graph, sem: asyncio.Semaphore):
    """Launch limit, parallel cap and per-launch accounting around one sub-agent type."""

    async def run(state: dict, config=None):
        desc = ""
        msgs = state.get("messages") or []
        if msgs:
            desc = str(getattr(msgs[-1], "content", ""))[:500]
        if kind == "span-investigator" and not any(iid in desc for iid in st.items):
            st.note("main_agent", "launch_refused_no_item", kind=kind)
            return {"messages": [AIMessage(content="Not run: a span-investigator needs a work item id from next_frontier "
                                                   "in its task. Use a hypothesis-tester for other questions.")]}
        with st.lock:
            n = len(st.launches)
            over = n >= st.limits["max_subagent_launches"]
            rec = {"n": n + 1, "type": kind, "input": desc, "t_start": round(time.time() - st.t_start, 2)}
            st.launches.append(rec)
        if over:
            if "max_subagent_launches" not in st.limits_hit:
                st.limits_hit.append("max_subagent_launches")
            rec.update(status="refused_limit", duration_s=0, tokens=0)
            st.note("main_agent", "launch_refused_limit", kind=kind)
            return {"messages": [AIMessage(content="LIMIT: the maximum number of sub-agent launches was reached; "
                                                   "this task was not run. Submit the best report you can.")]}
        files_before = set(p.name for p in (st.files / "evidence").glob("*.json"))
        counter = _Counter()
        async with sem:
            t0 = time.time()
            try:
                cfg = merge_configs(config or {}, {"callbacks": [counter], "metadata": {"lc_agent_name": kind}})
                out = await graph.ainvoke(state, cfg)
                rec["status"] = "ok"
                out = _record_structured(st, kind, desc, out, rec)
            except Exception as e:
                rec["status"] = f"error: {e!r}"[:300]
                out = {"messages": [AIMessage(content=f"sub-agent failed: {e!r}"[:500])]}
            rec["duration_s"] = round(time.time() - t0, 2)
        rec.update(tokens=counter.prompt + counter.completion, prompt_tokens=counter.prompt,
                   completion_tokens=counter.completion, llm_calls=counter.calls)
        rec["output_files"] = sorted(set(p.name for p in (st.files / "evidence").glob("*.json")) - files_before)
        return out

    return RunnableLambda(func=lambda s, c=None: asyncio.run(run(s, c)), afunc=run, name=kind)


def _limits(st: RunState, name: str) -> list:
    """Bound each sub-agent run: blocked tools after N calls (it must then answer), hard stop on model calls."""
    lim = st.limits
    return [MalformedCallRetry(st),
            ToolCallLimitMiddleware(run_limit=lim["subagent_tool_calls"].get(name, 10), exit_behavior="continue"),
            ModelCallLimitMiddleware(run_limit=lim["subagent_model_calls"], exit_behavior="end")]


def build_subagents(st: RunState, llm, tools: dict, sem: asyncio.Semaphore, critic: bool) -> list[dict]:
    backend = FilesystemBackend(root_dir=str(st.files), virtual_mode=True)
    specs = [
        ("span-investigator", "Investigates ONE work item (flagged span or anomalous service). Task description: "
                              "the work item id only.", "investigator", INVESTIGATOR_TOOLS, FindingIn),
        ("hypothesis-tester", "Tests ONE hypothesis the traces cannot show (node problem, shared dependency, code bug, "
                              "one replica vs whole service). Task description: the hypothesis and the service or node.",
         "tester", TESTER_TOOLS, HypothesisIn),
    ]
    if critic:
        specs.append(("critic", "Tries to break the draft report (report/draft.json) using the evidence files. "
                                "Launch once after write_draft.", "critic", CRITIC_TOOLS, CriticIn))
    out = []
    for name, desc, pname, tnames, schema in specs:
        g = create_deep_agent(model=llm, permissions=NO_WRITES, tools=[tools[t] for t in tnames], system_prompt=prompt(pname),
                              backend=backend, name=name, response_format=schema, middleware=_limits(st, name))
        out.append({"name": name, "description": desc, "runnable": _wrap_subagent(st, name, g, sem)})
    return out


def build_main_agent(st: RunState, llm, critic: bool = True):
    tools = build_tools(st)
    sem = asyncio.Semaphore(st.limits["parallel_subagents"])
    subagents = build_subagents(st, llm, tools, sem, critic)
    backend = FilesystemBackend(root_dir=str(st.files), virtual_mode=True)
    names = [t for t in MAIN_TOOLS if t in tools]
    return create_deep_agent(model=llm, permissions=NO_WRITES, tools=[tools[t] for t in names], system_prompt=prompt("main"),
                             subagents=subagents, backend=backend, name="main",
                             middleware=[TodoListMiddleware(), MalformedCallRetry(st),
                                         ModelCallLimitMiddleware(run_limit=st.limits["main_model_calls"], exit_behavior="end")])


def build_single_agent(st: RunState, llm):
    """V1 (Part 2 ablation): one agent, all tools, no sub-agents."""
    tools = build_tools(st)
    backend = FilesystemBackend(root_dir=str(st.files), virtual_mode=True)
    names = sorted(set(MAIN_TOOLS + INVESTIGATOR_TOOLS + TESTER_TOOLS + ["write_finding", "write_hypothesis"]))
    return create_deep_agent(model=llm, permissions=NO_WRITES, tools=[tools[t] for t in names], system_prompt=prompt("single"),
                             backend=backend, middleware=[TodoListMiddleware(), MalformedCallRetry(st)], name="single")


def build_synthesizer(st: RunState, llm, critic: bool = True):
    """V2 code-loop synthesizer: no investigation tools, only evidence reading, ranking, drafting and the critic."""
    tools = build_tools(st)
    sem = asyncio.Semaphore(st.limits["parallel_subagents"])
    subs = [s for s in build_subagents(st, llm, tools, sem, critic) if s["name"] in ("critic", "hypothesis-tester")]
    backend = FilesystemBackend(root_dir=str(st.files), virtual_mode=True)
    names = ["evidence_summary", "candidate_rank", "fault_indicators", "topology", "path_to_symptom", "write_draft", "submit_report"]
    return create_deep_agent(model=llm, permissions=NO_WRITES, tools=[tools[t] for t in names], system_prompt=prompt("synth"),
                             subagents=subs, backend=backend, name="main", middleware=[MalformedCallRetry(st)])


def build_investigator(st: RunState, llm):
    tools = build_tools(st)
    backend = FilesystemBackend(root_dir=str(st.files), virtual_mode=True)
    return create_deep_agent(model=llm, permissions=NO_WRITES, tools=[tools[t] for t in INVESTIGATOR_TOOLS], system_prompt=prompt("investigator"),
                             backend=backend, name="span-investigator", response_format=FindingIn,
                             middleware=_limits(st, "span-investigator"))

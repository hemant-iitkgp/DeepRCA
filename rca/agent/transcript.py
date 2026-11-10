"""Transcript logging (SPEC 3.5): every LLM call and tool call to runs/<run_id>/<case_id>/transcript.jsonl,
plus token and wall-clock limit enforcement (SPEC 3.6)."""
from __future__ import annotations

import json
import threading
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from rca.agent.state import LimitHit, RunState


def _agent_of(metadata: dict | None, tags: list | None) -> str:
    md = metadata or {}
    return str(md.get("lc_agent_name") or md.get("langgraph_node") or "main")


class TranscriptLogger(BaseCallbackHandler):
    raise_error = True  # a LimitHit raised in on_chat_model_start must stop the run

    def __init__(self, st: RunState, path, expected_snapshot: str | None, prices: dict):
        self.st = st
        self.path = path
        self.expected = expected_snapshot
        self.prices = prices
        self.lock = threading.Lock()
        self.starts: dict[UUID, tuple[float, str]] = {}
        self.calls = 0
        self.prompt_tokens = 0
        self.cached_tokens = 0
        self.completion_tokens = 0
        self.snapshots: set[str] = set()
        self.fingerprints: set[str] = set()
        self.by_agent: dict[str, dict] = {}
        self.f = open(path, "a", encoding="utf-8")

    def _write(self, rec: dict) -> None:
        with self.lock:
            self.f.write(json.dumps(rec, default=str) + "\n")
            self.f.flush()

    def on_chat_model_start(self, serialized, messages, *, run_id: UUID, parent_run_id=None, tags=None,
                            metadata=None, **kwargs: Any) -> None:
        self.st.check_limits()
        agent = _agent_of(metadata, tags)
        self.starts[run_id] = (time.time(), agent)
        msgs = []
        for m in messages[0]:
            msgs.append({"role": m.type, "content": m.content if isinstance(m.content, str) else json.dumps(m.content, default=str),
                         "tool_calls": getattr(m, "tool_calls", None) or None,
                         "tool_call_id": getattr(m, "tool_call_id", None)})
        self._write({"event": "llm_start", "run_id": str(run_id), "agent": agent, "t": time.time(), "messages": msgs})

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        t0, agent = self.starts.pop(run_id, (time.time(), "?"))
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        meta = getattr(msg, "response_metadata", {}) or {}
        usage = getattr(msg, "usage_metadata", None) or {}
        pt, ct = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        cached = int((usage.get("input_token_details") or {}).get("cache_read", 0))
        snap = meta.get("model_name") or meta.get("model")
        fp = meta.get("system_fingerprint")
        with self.lock:
            self.calls += 1
            self.prompt_tokens += pt
            self.completion_tokens += ct
            self.cached_tokens += cached
            if snap:
                self.snapshots.add(snap)
            if fp:
                self.fingerprints.add(fp)
            a = self.by_agent.setdefault(agent, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
            a["calls"] += 1
            a["prompt_tokens"] += pt
            a["completion_tokens"] += ct
            self.st.tokens = self.prompt_tokens + self.completion_tokens
        self._write({"event": "llm_end", "run_id": str(run_id), "agent": agent, "latency_s": round(time.time() - t0, 3),
                     "model": snap, "system_fingerprint": fp, "prompt_tokens": pt, "completion_tokens": ct,
                     "cached_tokens": cached, "content": msg.content if msg is not None else gen.text,
                     "tool_calls": getattr(msg, "tool_calls", None)})
        if self.expected and snap and snap != self.expected:
            raise RuntimeError(f"model snapshot drift: expected {self.expected}, got {snap}")

    def on_tool_start(self, serialized, input_str, *, run_id: UUID, metadata=None, tags=None, **kwargs) -> None:
        self._write({"event": "tool_start", "run_id": str(run_id), "agent": _agent_of(metadata, tags),
                     "tool": (serialized or {}).get("name"), "input": str(input_str)[:4000], "t": time.time()})

    def on_tool_end(self, output, *, run_id: UUID, **kwargs) -> None:
        content = getattr(output, "content", output)
        self._write({"event": "tool_end", "run_id": str(run_id), "output": str(content)[:6000], "t": time.time()})

    def on_tool_error(self, error, *, run_id: UUID, **kwargs) -> None:
        self._write({"event": "tool_error", "run_id": str(run_id), "error": repr(error)[:2000], "t": time.time()})

    def cost_usd(self) -> float:
        p = self.prices
        if p.get("price_input_per_mtok") is None:
            return float("nan")  # no published price: tokens are recorded, cost is computed later from billing
        uncached = self.prompt_tokens - self.cached_tokens
        cached_price = p.get("price_cached_input_per_mtok") or p["price_input_per_mtok"]
        return (uncached * p["price_input_per_mtok"] + self.cached_tokens * cached_price
                + self.completion_tokens * p["price_output_per_mtok"]) / 1e6

    def close(self) -> None:
        self.f.close()

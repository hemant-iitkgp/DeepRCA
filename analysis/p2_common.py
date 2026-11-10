"""Shared loading for the Part 2 Phase 8 analyses of DeepRCA's stored runs (no new LLM calls).

`load_cases(tag, run)` returns the per-case table written by analysis/wave_report.py (results/wave_<tag>_cases.csv)
with list columns decoded and `run_dir` pointing at runs/<run>/<case_id>/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rca.paths import RESULTS_DIR, RUNS_DIR  # noqa: E402


def load_cases(tag: str = "w12_r1", run: str = "test_r1") -> pd.DataFrame:
    d = pd.read_csv(RESULTS_DIR / f"wave_{tag}_cases.csv")
    for c in ("ranked_v3", "ranked_v4", "ranked_indicators", "rejection_reasons", "limits_hit"):
        if c in d:
            d[c] = d[c].map(lambda x: json.loads(x) if isinstance(x, str) else x)
    d["v3_hit1"] = d["v3_hit1"].astype(bool)
    d["control_hit1"] = d["control_hit1"].astype(bool)
    d["run_dir"] = d["case_id"].map(lambda c: RUNS_DIR / run / c)
    return d


def provenance(run_dir: Path) -> dict:
    p = Path(run_dir) / "provenance.json"
    return json.loads(p.read_text()) if p.exists() else {}


def findings(run_dir: Path) -> list[dict]:
    ev = Path(run_dir) / "files" / "evidence"
    return [json.loads(p.read_text()) for p in sorted(ev.glob("span_*.json"))] if ev.exists() else []


def hypotheses(run_dir: Path) -> list[dict]:
    ev = Path(run_dir) / "files" / "evidence"
    return [json.loads(p.read_text()) for p in sorted(ev.glob("hyp_*.json"))] if ev.exists() else []


def tool_calls(run_dir: Path) -> list[dict]:
    """Every tool call in the transcript: agent, tool, input, output (output joined from tool_end by run_id)."""
    p = Path(run_dir) / "transcript.jsonl"
    if not p.exists():
        return []
    starts, out = {}, []
    for line in p.open():
        r = json.loads(line)
        if r["event"] == "tool_start":
            starts[r["run_id"]] = {"agent": r.get("agent"), "tool": r.get("tool"), "input": r.get("input"), "t": r.get("t")}
            out.append(starts[r["run_id"]])
        elif r["event"] == "tool_end" and r["run_id"] in starts:
            starts[r["run_id"]]["output"] = r.get("output")
    return out


def save(df: pd.DataFrame, name: str) -> Path:
    p = RESULTS_DIR / name
    df.to_csv(p, index=False)
    return p

"""Scoring with RCAEval's own Evaluator.

The rank construction copies RCAEval `main.py` (commit 2fca61b): service-level
ranks cut each string at the first "_" and strip "-db", dropping repeats; the
indicator-level answer maps the fault type to an indicator name. The metrics
(AC@k, Avg@k) come from `RCAEval.benchmark.evaluation.Evaluator`, never from
our own code.
"""
from __future__ import annotations

from RCAEval.benchmark.evaluation import Evaluator
from RCAEval.classes.graph import Node

# main.py: fault -> indicator answered at the fine-grained level.
# RE1 has no disk metric, so its disk faults are scored against latency.
_INDICATOR = {"cpu": "cpu", "mem": "mem", "delay": "latency", "loss": "latency", "socket": "socket"}


def indicator_for(fault: str, dataset: str) -> str | None:
    if fault == "disk":
        return "latency" if dataset.startswith("RE1") else "diskio"
    return _INDICATOR.get(fault)  # None for RE3 f1..f5: not defined by RCAEval


def service_nodes(ranked: list[str]) -> list[Node]:
    nodes = [Node(x.split("_")[0].replace("-db", ""), "unknown") for x in ranked]
    out: list[Node] = []
    for n in nodes:
        if n not in out:
            out.append(n)
    return out


def indicator_nodes(ranked: list[str]) -> list[Node]:
    return [Node(x.split("_")[0], x.split("_")[1] if "_" in x else "unknown") for x in ranked]


def gt_service_key(gt_service: str) -> str:
    """The service name as RCAEval compares it (directory name, "-db" stripped)."""
    return gt_service.split("_")[0].replace("-db", "")


def score_cases(rows: list[dict], level: str = "service", max_k: int = 5) -> dict:
    """rows: dicts with keys ranked (list[str]), gt_service, fault, dataset.

    Returns AC@1..max_k, Avg@max_k and n, computed by RCAEval's Evaluator.
    Indicator level skips cases whose fault has no RCAEval indicator.
    """
    ev = Evaluator(max_k=max_k)
    n = 0
    for r in rows:
        if level == "service":
            ev.add_case(ranks=service_nodes(r["ranked"]), answer=Node(gt_service_key(r["gt_service"]), "unknown"))
        else:
            ind = indicator_for(r["fault"], r["dataset"])
            if ind is None:
                continue
            ev.add_case(ranks=indicator_nodes(r["ranked"]), answer=Node(r["gt_service"], ind))
        n += 1
    if n == 0:
        return {"n": 0}
    out = {f"AC@{k}": ev.accuracy(k) for k in range(1, max_k + 1)}
    out[f"Avg@{max_k}"] = ev.average(max_k)
    out["n"] = n
    return out


def hit_at(ranked: list[str], gt_service: str, k: int) -> bool:
    """Per-case service-level hit, using the same rank construction as the Evaluator."""
    ev = Evaluator(max_k=max(k, 1))
    ev.add_case(ranks=service_nodes(ranked), answer=Node(gt_service_key(gt_service), "unknown"))
    return ev.accuracy(k) == 1.0

"""topology: callers, callees, pods, replicas and node of a service.

The call graph is the static per-system graph in data/topology/ (built from normal-period traces,
see rca/adapter/topology.py) merged with the edges seen in this case's own baseline traces.
"""
from __future__ import annotations

import functools
import json

import networkx as nx

from rca.paths import TOPOLOGY_DIR
from rca.tools.data import CaseData


@functools.lru_cache(maxsize=16)
def static_graph(system: str) -> dict:
    p = TOPOLOGY_DIR / f"{system}.json"
    if not p.exists():
        return {"services": [], "edges": [], "source": "none"}
    return json.loads(p.read_text())


_GRAPHS: dict[str, nx.DiGraph] = {}


def case_graph(cd: CaseData) -> nx.DiGraph:
    if cd.cache_key not in _GRAPHS:
        _GRAPHS[cd.cache_key] = _build_case_graph(cd)
    return _GRAPHS[cd.cache_key]


def _build_case_graph(cd: CaseData) -> nx.DiGraph:
    g = nx.DiGraph()
    st = static_graph(cd.case["system"])
    rn = cd.rename
    for a, b, n in st["edges"]:
        g.add_edge(rn.get(a, a), rn.get(b, b), weight=n)
    if cd.spans is not None:
        from rca.tools.traces import span_table
        s = span_table(cd)
        b0, b1 = cd.baseline()
        s = s[(s["ts_start"] >= b0) & (s["ts_start"] < b1)]
        for (a, b), n in s[s["is_cross_call"]].groupby(["caller_service", "service"]).size().items():
            if a != b:
                g.add_edge(a, b, weight=int(n))
        for (a, b), n in s[s["callee"].notna()].groupby(["service", "callee"]).size().items():
            if a != b:
                g.add_edge(a, b, weight=int(n))
    g.add_nodes_from(cd.services)
    return g


def topology(cd: CaseData, service: str) -> dict:
    g = case_graph(cd)
    ent = cd.entities
    e = ent[ent["service"] == service]
    pods = sorted(e["pod"].dropna().unique())
    nodes = sorted(e["node"].dropna().unique())
    co_located = {}
    for nd in nodes:
        co_located[nd] = sorted(set(ent.loc[(ent["node"] == nd) & (ent["service"] != service), "service"]))[:15]
    has_graph = g.number_of_edges() > 0
    out = {
        "service": service,
        "known_service": service in cd.services,
        "callers": sorted(g.predecessors(service)) if service in g else [],
        "callees": sorted(g.successors(service)) if service in g else [],
        "pods": pods, "replicas": len(pods), "nodes": nodes, "other_services_on_same_node": co_located,
    }
    if not has_graph:
        out["note"] = "no call graph is available for this case (no traces); callers/callees unknown"
    return out


def path_exists(cd: CaseData, a: str, b: str) -> bool | None:
    """True if a and b are connected in the call graph (either direction), None if there is no graph."""
    g = case_graph(cd)
    if g.number_of_edges() == 0:
        return None
    if a == b:
        return True
    if a not in g or b not in g:
        return False
    u = g.to_undirected()
    return nx.has_path(u, a, b)


def depth_order(cd: CaseData, services: list[str]) -> list[str]:
    """Order services from callee to caller (deepest first) using the call graph; ties by name."""
    g = case_graph(cd)
    if g.number_of_edges() == 0:
        return list(services)
    try:
        cond = nx.condensation(g)
        order = list(nx.topological_sort(cond))
        rank = {}
        for i, c in enumerate(order):
            for n in cond.nodes[c]["members"]:
                rank[n] = i
    except Exception:
        rank = {}
    return sorted(services, key=lambda s: (-rank.get(s, -1), s))

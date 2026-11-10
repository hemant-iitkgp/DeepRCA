"""submit_report checks (SPEC 7.6). Every failure is listed, not just the first."""
from __future__ import annotations

from rca.guardrails.support import positive_evidence
from rca.tools.topology import case_graph


def symptom_services(state) -> set[str]:
    """Where the failure is visible: entry services of the selected anomalous traces; without traces,
    services whose latency or error metrics are anomalous."""
    s = {t["entry_service"] for t in state.selected_traces}
    if s:
        return s
    from rca.tools.metrics import entity_anomalies
    from rca.paths import system_config

    cd = state.cd
    w0, w1 = cd.window()
    n = system_config()["tools"]["metric_n_sigma"]
    out = set()
    for svc in cd.services:
        if any(a["type"] in ("latency", "error") for a in entity_anomalies(cd, svc, w0, w1, n)):
            out.add(svc)
    return out


def path_to_symptom(state, service: str) -> list[str] | None:
    """Shortest connected path in the call graph from `service` to the nearest symptom service."""
    import networkx as nx

    g = case_graph(state.cd)
    if g.number_of_edges() == 0 or service not in g:
        return None
    u = g.to_undirected()
    best = None
    for s in symptom_services(state):
        if s in u and nx.has_path(u, service, s):
            p = nx.shortest_path(u, service, s)
            if best is None or len(p) < len(best):
                best = p
    return best


def services_with_positive_evidence(state) -> list[str]:
    from rca.guardrails.support import cited_types

    return [s for s in state.cd.services if cited_types(state, s) and positive_evidence(state, s)]


def normalise_report(report: dict) -> dict:
    rs = report.get("ranked_services") or []
    services = []
    for r in rs:
        services.append(r if isinstance(r, dict) else {"service": str(r), "source": "evidence"})
    report["ranked_services"] = services
    return report


def check_report(state, report: dict) -> list[str]:
    cd = state.cd
    fails: list[str] = []
    report = normalise_report(report)
    names = [r.get("service") for r in report["ranked_services"]]

    # 1. coverage
    unc = state.uncovered()
    if unc:
        fails.append(f"COVERAGE: {len(unc)} flagged work items have no finding file: "
                     + ", ".join(f"{u['id']} ({u.get('blamed_service')})" for u in unc[:10]))

    # 2. critic
    if state.variant.get("critic", "on") == "on":
        crit = state.critic()
        if crit is None:
            fails.append("CRITIC: no critic file (evidence/critic.json); launch the critic on the draft first")
        elif crit.get("verdict") == "fail":
            issues = crit.get("issues") or []
            resp = report.get("critic_response") or []
            answered = [r for r in resp if isinstance(r, dict) and str(r.get("response", "")).strip()]
            if len(answered) < len(issues):
                fails.append(f"CRITIC: the critic failed the draft with {len(issues)} issues and the report answers "
                             f"{len(answered)}. Add critic_response entries, one per issue, each "
                             '{"issue": <the issue>, "response": <what you checked or changed>}. Issues: '
                             + " | ".join(f"({i + 1}) {str(x)[:200]}" for i, x in enumerate(issues)))

    # 4. ranked list shape
    known = set(cd.services)
    need = min(5, len(known))
    if len(names) < need:
        fails.append(f"RANKING: {len(names)} services ranked; at least {need} required (fill the tail from "
                     "candidate_rank and mark those entries source=fallback)")
    dups = sorted({n for n in names if names.count(n) > 1})
    if dups:
        fails.append(f"RANKING: duplicate services {dups}")
    unknown = [n for n in names if n not in known]
    if unknown:
        fails.append(f"RANKING: services not in this case's entity list: {unknown[:8]}")

    # 3. positive evidence for top-1
    if names:
        top = names[0]
        pe = positive_evidence(state, top)
        if not pe:
            fails.append(f"EVIDENCE: top-1 '{top}' has no positive evidence (own anomalous metric, own anomalous log "
                         "template, a caller-vs-callee gap pointing at it, or a stack trace) that is both cited in a "
                         "finding/hypothesis file and confirmed in the data. 'Nothing anomalous upstream' is not evidence. "
                         f"Services that do have such evidence: {services_with_positive_evidence(state)[:10]}. Either rank "
                         "one of them first or launch a hypothesis-tester to gather evidence for your candidate.")

        # 5. evidence path
        path = report.get("evidence_path") or []
        g = case_graph(cd)
        if g.number_of_edges() > 0:
            sym = symptom_services(state)
            hint = path_to_symptom(state, top)
            hint_txt = f" A connected path from '{top}' (from path_to_symptom): {hint}." if hint else ""
            if not path or path[0] != top:
                fails.append(f"PATH: evidence_path must start at the top-1 service '{top}'.{hint_txt}")
            elif sym and path[-1] not in sym:
                fails.append(f"PATH: evidence_path must end at a symptom service, one of {sorted(sym)[:8]}.{hint_txt}")
            else:
                u = g.to_undirected()
                bad = [(a, b) for a, b in zip(path, path[1:]) if not u.has_edge(a, b)]
                if bad:
                    fails.append(f"PATH: these consecutive services are not connected in the call graph: {bad[:5]}.{hint_txt}")
    return fails

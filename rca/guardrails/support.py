"""Code-computed support for candidate services, and verification of positive evidence.

Positive evidence (SPEC 3.4 rule 2) for service S is one of: S's own anomalous metric, S's own
anomalous log template, a caller-vs-callee gap (or slow unobserved call) pointing at S, or a stack
trace in S's logs. A finding or hypothesis file must cite it AND code must confirm it in the data,
so a report cannot rest on a claim the telemetry does not show. "Nothing anomalous upstream" is
never one of these types.
"""
from __future__ import annotations

from rca.paths import system_config
from rca.tools.logs import log_anomalies
from rca.tools.metrics import entity_anomalies

# "status": calls into the service fail (error status seen by its callers) - read as part of the SPEC's
# "caller-vs-callee" evidence, since the caller observes a failure the callee causes (see WORKLOG).
POSITIVE_TYPES = {"metric", "log", "edge_gap", "stack_trace", "status"}


def ev_items(lst) -> list[dict]:
    """Evidence entries as dicts; a plain-text entry (no type) carries no positive evidence type."""
    return [e if isinstance(e, dict) else {"type": "other", "detail": str(e)} for e in (lst or [])]


def finding_target(f: dict, items: dict) -> str | None:
    """The service a finding blames, or None when it blames nothing."""
    if not f.get("abnormal"):
        return None
    blame = str(f.get("blame", "none"))
    if blame == "self":
        return f.get("service")
    if blame.startswith("edge:") and "->" in blame:
        return blame.split("->", 1)[1].strip()
    if blame.startswith("child:"):
        cid = blame.split(":", 1)[1].strip()
        it = items.get(cid)
        return it.get("blamed_service") if it else None
    return None


def support_scores(state) -> dict[str, float]:
    sc: dict[str, float] = {}
    items = state.items
    for iid, f in state.findings().items():
        tgt = finding_target(f, items)
        if tgt:
            sc[tgt] = sc.get(tgt, 0.0) + 0.5 + float(f.get("confidence", 0.5) or 0.5)
    for h in state.hypotheses():
        if h.get("verdict") == "supported" and h.get("service"):
            sc[h["service"]] = sc.get(h["service"], 0.0) + 0.5
    return sc


def _verify(cd, service: str, typ: str) -> bool:
    w0, w1 = cd.window()
    if typ == "metric":
        return bool(entity_anomalies(cd, service, w0, w1, system_config()["tools"]["metric_n_sigma"]))
    if typ in ("log", "stack_trace"):
        if cd.logs is None:
            return False
        la = log_anomalies(cd, service)
        t = la.get("anomalous_templates", [])
        return any(x["stack_trace"] for x in t) if typ == "stack_trace" else bool(t)
    return False


def verified_types(state, service: str) -> set[str]:
    """Positive evidence types for `service` that code confirms in the data."""
    out = set()
    cache = state.__dict__.setdefault("_verify_cache", {})
    for typ in ("metric", "log", "stack_trace"):
        if (service, typ) not in cache:
            cache[(service, typ)] = _verify(state.cd, service, typ)
        if cache[(service, typ)]:
            out.add(typ)
    for it in state.items.values():
        rs = set(it.get("reasons", []))
        # a slow edge into the service (the service is the callee) or a slow call to it that it never reports
        if ("edge_gap" in rs and it.get("service") == service) or                 (it.get("unobserved_callee") == service and ("own_time" in rs or "edge_gap" in rs)):
            out.add("edge_gap")
        if "error_status" in rs and (it.get("unobserved_callee") == service or
                                     (it.get("service") == service and it.get("caller_service"))):
            out.add("status")
    return out


def cited_types(state, service: str) -> set[str]:
    """Positive evidence types cited for `service` in finding or hypothesis files."""
    out = set()
    items = state.items
    for f in state.findings().values():
        if finding_target(f, items) != service and f.get("service") != service:
            continue
        for e in ev_items(f.get("evidence_for")):
            if e.get("type") in POSITIVE_TYPES:
                out.add(e["type"])
    for h in state.hypotheses():
        if h.get("service") == service and h.get("verdict") != "refuted":
            for e in ev_items(h.get("evidence_for")):
                if e.get("type") in POSITIVE_TYPES:
                    out.add(e["type"])
    return out


def positive_evidence(state, service: str) -> set[str]:
    """Types both cited in an evidence file and confirmed in the data."""
    return cited_types(state, service) & verified_types(state, service)

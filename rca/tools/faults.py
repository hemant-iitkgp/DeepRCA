"""fault_indicators: deterministic fault-type evidence for one service (SPEC 7.2, 7.9).

Classes: resource (cpu, memory, disk, socket), network (delay, loss), code. Each candidate
cites the measurement behind it; the agent chooses one and must cite the indicator.
"""
from __future__ import annotations

from rca.paths import system_config
from rca.tools.data import CaseData
from rca.tools.logs import log_anomalies
from rca.tools.metrics import entity_anomalies


def _flagged_into(cd: CaseData, service: str, flagged: list[dict]) -> dict:
    """Summarise flagged spans that point at this service."""
    out = {"edge_gap": 0, "unobserved_call": 0, "own_time": 0, "error_status": 0}
    for f in flagged:
        if service not in (f.get("blamed_services") or [f.get("blamed_service")]):
            continue
        rs = set(f.get("reasons", []))
        if "edge_gap" in rs and f.get("service") == service:
            out["edge_gap"] += 1
        if f.get("unobserved_callee") == service:
            out["unobserved_call"] += 1
        elif "own_time" in rs:
            out["own_time"] += 1
        if "error_status" in rs:
            out["error_status"] += 1
    return out


def fault_indicators(cd: CaseData, service: str, flagged: list[dict] | None = None) -> dict:
    n = system_config()["tools"]["metric_n_sigma"]
    w0, w1 = cd.window()
    anoms = entity_anomalies(cd, service, w0, w1, n)
    by_type: dict[str, list] = {}
    for a in anoms:
        by_type.setdefault(a["type"], []).append(a)
    cands = []

    def add(fault, strength, evidence):
        cands.append({"fault_type": fault, "strength": round(float(strength), 1), "indicator": evidence})

    for typ, fault in [("cpu", "cpu"), ("memory", "memory"), ("disk", "disk")]:
        ups = [a for a in by_type.get(typ, []) if a["direction"] == "up"]
        if ups:
            a = ups[0]
            add(fault, a["peak_z"], f"{service}_{a['metric']} up, peak z {a['peak_z']}, onset +{a['onset_s_after_fault']}s")
    net = by_type.get("network", [])
    sock = [a for a in net if "socket" in a["metric"]]
    if sock:
        a = sock[0]
        add("socket", a["peak_z"], f"{service}_{a['metric']} {a['direction']}, peak z {a['peak_z']}")
    drops = [a for a in net if any(k in a["metric"] for k in ("drop", "error", "retrans"))]
    if drops:
        a = drops[0]
        add("loss", a["peak_z"], f"{service}_{a['metric']} {a['direction']}, peak z {a['peak_z']}")
    lat = [a for a in by_type.get("latency", []) if a["direction"] == "up"]
    fl = _flagged_into(cd, service, flagged or [])
    if fl["edge_gap"] or fl["unobserved_call"]:
        add("delay", 3.0 + fl["edge_gap"] + fl["unobserved_call"],
            f"{fl['edge_gap']} slow caller->callee edges and {fl['unobserved_call']} slow unobserved calls point at {service}")
    if lat:
        a = lat[0]
        add("delay", a["peak_z"] / 2, f"{service}_{a['metric']} up, peak z {a['peak_z']}")
    errs = by_type.get("error", [])
    if errs or fl["error_status"]:
        add("loss", 2.0 + fl["error_status"], f"error metrics/status: {[e['metric'] for e in errs[:2]]}, {fl['error_status']} error spans")
    if cd.logs is not None:
        la = log_anomalies(cd, service)
        tpls = la.get("anomalous_templates", [])
        stack = [t for t in tpls if t["stack_trace"]]
        errl = [t for t in tpls if t["error_level"]]
        if stack:
            add("code", 10.0, f"stack trace in {service} logs: {stack[0]['template'][:100]}")
        elif errl:
            add("code", 5.0, f"new/spiking error logs in {service}: {errl[0]['template'][:100]}")
        elif la.get("lines_expected_from_baseline", 0) > 20 and la.get("lines_window", 0) < 0.3 * la["lines_expected_from_baseline"]:
            add("code", 2.0, f"{service} log volume fell to {la['lines_window']} from expected {la['lines_expected_from_baseline']}")
    cands.sort(key=lambda c: -c["strength"])
    return {"service": service, "candidates": cands,
            "note": "deterministic candidates; choose one and cite its indicator, or say unknown"}

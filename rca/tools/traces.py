"""Trace evidence: own time, caller-vs-callee gaps, baselines, trace selection and flagged call trees.

Definitions (SPEC 7.2):
  own time  = span duration minus the union of its children's intervals (clipped to the span)
  edge gap  = caller-observed duration (the caller's client span) minus callee-reported duration
              (the callee's server span), defined when a span has exactly one child and that child
              belongs to another service
A client span with no child whose operation names another service is an *unobserved call*: its
callee is inferred by matching operation tokens to the case's entity names, and its whole duration
is time spent in that callee or on the network.

Abnormal (flagged) spans: a span is flagged when its own value is beyond its operation's baseline
p99 AND the operation is persistently shifted in the fault window (window p75 vs baseline p75,
in units of the baseline p50->p99 spread). Single slow outliers of an operation that is normal as a
whole are not flagged: heavy-tailed operations produce them in normal periods too. Error status is
flagged when the operation's error rate rises over baseline.
"""
from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

from rca.paths import system_config
from rca.tools.cache import cached
from rca.tools.data import CaseData

OWN_KEY = ["service", "operation"]
GAP_KEY = ["caller_service", "service", "operation"]


def _norm(s: str, prefix: str) -> str:
    n = re.sub(r"[^a-z0-9]", "", str(s).lower())
    if prefix and n.startswith(prefix) and len(n) > len(prefix):
        n = n[len(prefix):]
    for suf in system_config()["adapter"]["name_normalise"]["strip_suffixes"]:
        if n.endswith(suf) and len(n) > len(suf):
            n = n[: -len(suf)]
    if n.endswith("s") and len(n) >= 3:  # plural form of a name ("ads", "carts")
        n = n[:-1]
    return n


def _common_prefix(names: list[str]) -> str:
    ns = [re.sub(r"[^a-z0-9]", "", n.lower()) for n in names]
    if len(ns) < 3:
        return ""
    p = os.path.commonprefix(ns)
    return p if len(p) <= 4 else ""


def callee_matcher(services: list[str]):
    """Return f(operation) -> service named by the operation, or None. Built from the case's own entity names."""
    prefix = _common_prefix(services)
    by_norm: dict[str, str] = {}
    for s in services:
        k = _norm(s, prefix)
        if len(k) >= 2:
            by_norm.setdefault(k, s)

    def match(op: str) -> str | None:
        for tok in re.split(r"[^A-Za-z0-9-]+", str(op)):
            k = _norm(tok, prefix)
            if k in by_norm:
                return by_norm[k]
        return None

    return match


# --------------------------------------------------------------------------- span table
def _span_table(cd: CaseData) -> pd.DataFrame:
    s = cd.spans[["trace_id", "span_id", "parent_span_id", "service", "operation", "ts_start", "duration_ms", "status"]].copy()
    s = s.drop_duplicates(["trace_id", "span_id"]).reset_index(drop=True)
    s["operation"] = s["operation"].fillna("").astype(str)
    s["ts_end"] = s["ts_start"] + s["duration_ms"] / 1e3
    s["row"] = np.arange(len(s))
    key = pd.MultiIndex.from_arrays([s["trace_id"], s["span_id"]])
    pos = pd.Series(s["row"].values, index=key)
    pkey = pd.MultiIndex.from_arrays([s["trace_id"], s["parent_span_id"].fillna("")])
    prow = pos.reindex(pkey).values
    s["parent_row"] = np.where(np.isnan(prow), -1, prow).astype(np.int64)
    s["is_root"] = s["parent_row"] < 0

    # union of children intervals per parent, clipped to the parent
    ch = s[s["parent_row"] >= 0][["parent_row", "ts_start", "ts_end"]].sort_values(["parent_row", "ts_start"]).values
    union = np.zeros(len(s))
    n_child = np.bincount(s.loc[s["parent_row"] >= 0, "parent_row"].values, minlength=len(s))
    p_start, p_end = s["ts_start"].values, s["ts_end"].values
    cur, cs, ce, acc = -1, 0.0, 0.0, 0.0
    for pr, a, b in ch:
        pr = int(pr)
        a, b = max(a, p_start[pr]), min(b, p_end[pr])
        if pr != cur:
            if cur >= 0:
                union[cur] = acc + max(0.0, ce - cs)
            cur, cs, ce, acc = pr, a, b, 0.0
            continue
        if a > ce:
            acc += max(0.0, ce - cs)
            cs, ce = a, b
        else:
            ce = max(ce, b)
    if cur >= 0:
        union[cur] = acc + max(0.0, ce - cs)
    s["n_children"] = n_child
    s["own_ms"] = np.maximum(0.0, s["duration_ms"].values - union * 1e3)

    # edge gap: parent has exactly one child and it is in another service
    pr = s["parent_row"].values
    has_p = pr >= 0
    safe = np.where(has_p, pr, 0)
    par_service = np.where(has_p, s["service"].values[safe], None)
    par_dur = np.where(has_p, s["duration_ms"].values[safe], np.nan)
    par_nch = np.where(has_p, n_child[safe], 0)
    s["caller_service"] = par_service
    cross = has_p & (par_service != s["service"].values)
    s["edge_gap_ms"] = np.where(cross & (par_nch == 1), par_dur - s["duration_ms"].values, np.nan)
    s["is_cross_call"] = cross
    # a client span whose single child is the callee's server span: its own time IS the edge gap,
    # so it is not scored again as own time
    child_cross = np.zeros(len(s), dtype=bool)
    child_cross[pr[cross & (par_nch == 1)]] = True
    s["is_client_of_edge"] = child_cross

    # unobserved calls: leaf span whose operation names another service
    match = callee_matcher(cd.services)
    named = {op: match(op) for op in s["operation"].unique()}
    callee = s["operation"].map(named)
    s["callee"] = np.where((s["n_children"] == 0) & callee.notna() & (callee != s["service"]), callee, None)
    return s


def span_table(cd: CaseData) -> pd.DataFrame:
    return cached(cd.cache_key, "span_table", {"fs": cd.fault_start}, lambda: _span_table(cd))


def _signatures(s: pd.DataFrame) -> pd.Series:
    """Root row -> signature: root op plus the sorted distinct operations of its direct children."""
    kids = s[s["parent_row"] >= 0].groupby("parent_row")["operation"].agg(lambda x: "|".join(sorted(set(x))))
    roots = s[s["is_root"]]
    return pd.Series([f"{op}::{kids.get(r, '')}" for r, op in zip(roots["row"], roots["operation"])], index=roots["row"].values)


# --------------------------------------------------------------------------- baselines and window shifts
def _qstats(df: pd.DataFrame, keys: list[str], col: str, prefix: str) -> pd.DataFrame:
    g = df.groupby(keys)[col]
    q = g.quantile([0.5, 0.75, 0.99]).unstack()
    q.columns = [f"{prefix}50", f"{prefix}75", f"{prefix}99"]
    q[f"{prefix}n"] = g.size()
    return q


def _spread(p50, p99):
    return np.maximum.reduce([np.asarray(p99 - p50, float), 0.1 * np.abs(np.asarray(p50, float)),
                              np.full(np.shape(p50), system_config()["tools"]["min_abs_ms"])])


def _key_stats(cd: CaseData) -> dict:
    s = span_table(cd)
    b0, b1 = cd.baseline()
    w0, w1 = cd.window()
    b = s[(s["ts_start"] >= b0) & (s["ts_start"] < b1)]
    w = s[(s["ts_start"] >= w0) & (s["ts_start"] <= w1)]
    own_b = _qstats(b[~b["is_client_of_edge"]], OWN_KEY, "own_ms", "b")
    own_w = _qstats(w[~w["is_client_of_edge"]], OWN_KEY, "own_ms", "w")
    gb = b[b["edge_gap_ms"].notna()]
    gw = w[w["edge_gap_ms"].notna()]
    gap_b = _qstats(gb, GAP_KEY, "edge_gap_ms", "b")
    gap_w = _qstats(gw, GAP_KEY, "edge_gap_ms", "w")
    own = own_b.join(own_w, how="outer")
    gap = gap_b.join(gap_w, how="outer")
    for t in (own, gap):
        t["spread"] = _spread(t["b50"], t["b99"])
        t["shift"] = (t["w75"] - t["b75"]) / t["spread"]
    err_b = b.groupby(OWN_KEY)["status"].apply(lambda x: float((x > 0).mean()))
    err_w = w.groupby(OWN_KEY)["status"].apply(lambda x: float((x > 0).mean()))
    err = pd.DataFrame({"err_b": err_b, "err_w": err_w}).fillna(0.0)
    roots_b = b[b["is_root"]]
    entry = roots_b.groupby(OWN_KEY)["duration_ms"].quantile([0.5, 0.99]).unstack()
    entry.columns = ["e50", "e99"]
    return {"own": own, "gap": gap, "err": err, "entry": entry}


def key_stats(cd: CaseData) -> dict:
    return cached(cd.cache_key, "key_stats", {"fs": cd.fault_start, "b": cd.baseline(), "w": cd.window()},
                  lambda: _key_stats(cd))


def _score(t: pd.DataFrame, ks: dict) -> pd.DataFrame:
    """Vectorised own-time / edge-gap scores and flags for a set of spans."""
    cfg = system_config()["tools"]
    t = t.copy()
    o = ks["own"].reindex(pd.MultiIndex.from_frame(t[OWN_KEY]))
    g = ks["gap"].reindex(pd.MultiIndex.from_frame(t[GAP_KEY].fillna("")))
    e = ks["err"].reindex(pd.MultiIndex.from_frame(t[OWN_KEY]))
    t["own_z"] = ((t["own_ms"].values - o["b50"].values) / o["spread"].values)
    t["own_shift"] = o["shift"].values
    t["gap_z"] = ((t["edge_gap_ms"].values - g["b50"].values) / g["spread"].values)
    t["gap_shift"] = g["shift"].values
    min_n, thr_z, thr_shift = 5, cfg["own_time_z"], cfg["key_shift"]
    own_ok = (o["bn"].fillna(0).values >= min_n) & ~t["is_client_of_edge"].values
    t["flag_own"] = own_ok & (t["own_ms"].values > o["b99"].values + cfg["min_abs_ms"]) & (t["own_z"].values > thr_z) \
        & (t["own_shift"].values > thr_shift)
    gap_ok = (g["bn"].fillna(0).values >= min_n)
    t["flag_gap"] = gap_ok & (t["edge_gap_ms"].values > g["b99"].values + cfg["min_abs_ms"]) \
        & (t["gap_z"].values > cfg["edge_gap_z"]) & (t["gap_shift"].values > thr_shift)
    eb, ew = e["err_b"].fillna(0).values, e["err_w"].fillna(0).values
    t["flag_err"] = (t["status"].values > 0) & (ew > eb + cfg["error_rate_rise"]) & (ew > 2 * eb)
    t["flagged"] = t["flag_own"] | t["flag_gap"] | t["flag_err"]
    reasons = []
    for fo, fg, fe in zip(t["flag_own"].values, t["flag_gap"].values, t["flag_err"].values):
        r = []
        if fo:
            r.append("own_time")
        if fg:
            r.append("edge_gap")
        if fe:
            r.append("error_status")
        reasons.append(r)
    t["reasons"] = reasons
    # excess latency explained by flagged parts of the span (ms over the operation's baseline median)
    t["excess_ms"] = np.where(t["flag_own"], t["own_ms"].values - o["b50"].fillna(0).values, 0.0) \
        + np.where(t["flag_gap"], t["edge_gap_ms"].fillna(0).values - g["b50"].fillna(0).values, 0.0)
    return t


def blamed_services(r) -> list[str]:
    """Services a flagged span points at: an unobserved callee, both ends of a slow edge, or itself."""
    out = []
    if isinstance(r.get("callee"), str) and r.get("callee"):
        out += [r["callee"]]
    if "edge_gap" in r.get("reasons", []):
        out += [r["service"], r["caller_service"]]
    if "own_time" in r.get("reasons", []) and not out:
        out += [r["service"]]
    if "error_status" in r.get("reasons", []):
        out += [r["service"]]
    seen = []
    for s in out:
        if isinstance(s, str) and s not in seen:
            seen.append(s)
    return seen


def _window_scores(cd: CaseData) -> pd.DataFrame:
    s = span_table(cd)
    w0, w1 = cd.window()
    return _score(s[(s["ts_start"] >= w0) & (s["ts_start"] <= w1)], key_stats(cd))


def window_scores(cd: CaseData) -> pd.DataFrame:
    return cached(cd.cache_key, "window_scores", {"fs": cd.fault_start, "w": cd.window()}, lambda: _window_scores(cd))


# --------------------------------------------------------------------------- select_traces
def select_traces(cd: CaseData, k: int | None = None) -> list[dict]:
    """Rank fault-window traces by entry latency over baseline and errors, counting only latency
    explained by flagged spans (persistent shifts), and prefer traces that cover new flagged operations."""
    cfg = system_config()["tools"]
    k = k or cfg["select_traces_k"]
    ws = window_scores(cd)
    if ws.empty:
        return []
    ks = key_stats(cd)
    per = ws.groupby("trace_id").agg(excess_ms=("excess_ms", "sum"), n_flagged=("flagged", "sum"),
                                     err=("flag_err", "max"), n_spans=("row", "size"))
    roots = ws[ws["is_root"]].drop_duplicates("trace_id").set_index("trace_id")
    per = per.join(roots[["service", "operation", "duration_ms"]], how="inner")
    ent = ks["entry"].reindex(pd.MultiIndex.from_frame(per[["service", "operation"]]))
    spread = _spread(ent["e50"].values, ent["e99"].values)
    per["z"] = np.nan_to_num((per["duration_ms"].values - ent["e50"].values) / spread)
    per = per[(per["n_flagged"] > 0)]
    if per.empty:
        return []
    flagged_keys = ws[ws["flagged"]].assign(key=lambda d: d["service"] + "|" + d["operation"] + "|" + d["reasons"].map(",".join))
    keys_by_trace = flagged_keys.groupby("trace_id")["key"].agg(set)
    per["score"] = per["excess_ms"] + np.where(per["err"], 1e6, 0.0)
    per = per.sort_values(["score", "z"], ascending=False).head(400)
    chosen, covered = [], set()
    cand = list(per.index)
    while cand and len(chosen) < k:
        best = max(cand, key=lambda tid: (len(keys_by_trace.get(tid, set()) - covered), per.loc[tid, "score"]))
        chosen.append(best)
        covered |= keys_by_trace.get(best, set())
        cand.remove(best)
    out = []
    for tid in chosen:
        r = per.loc[tid]
        out.append({"trace_id": tid, "entry_service": r["service"], "entry_operation": str(r["operation"])[:80],
                    "duration_ms": round(float(r["duration_ms"]), 2), "z": round(float(r["z"]), 1),
                    "explained_excess_ms": round(float(r["excess_ms"]), 1), "error": bool(r["err"]),
                    "n_spans": int(r["n_spans"]), "n_flagged_spans": int(r["n_flagged"])})
    return out


# --------------------------------------------------------------------------- trace_tree
def score_spans(cd: CaseData, trace_id: str) -> pd.DataFrame:
    """All spans of one trace with own-time / edge-gap scores and flags."""
    s = span_table(cd)
    t = s[s["trace_id"] == trace_id]
    if t.empty:
        return t.assign(own_z=[], gap_z=[], reasons=[], flagged=[])
    return _score(t, key_stats(cd))


def trace_tree(cd: CaseData, trace_id: str) -> dict:
    """Compact flagged tree. Flagged spans and their ancestors are shown; normal subtrees are counted as pruned.
    Repeated flagged siblings with the same ancestry path are grouped; the worst one is the representative."""
    t = score_spans(cd, trace_id)
    if t.empty:
        return {"trace_id": trace_id, "error": "trace not found in this case"}
    by_row = t.set_index("row")
    keep = set()
    for r in t[t["flagged"]].itertuples():
        cur = r.row
        while cur >= 0 and cur in by_row.index and cur not in keep:
            keep.add(cur)
            cur = int(by_row.loc[cur, "parent_row"])
    path: dict[int, tuple] = {}

    def path_of(row: int) -> tuple:
        if row in path:
            return path[row]
        pr = int(by_row.loc[row, "parent_row"])
        base = path_of(pr) if pr >= 0 and pr in by_row.index else ()
        path[row] = base + ((by_row.loc[row, "service"], by_row.loc[row, "operation"]),)
        return path[row]

    def fnum(x, nd=1):
        return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)

    groups: dict[tuple, list] = {}
    for r in t[t["row"].isin(keep)].sort_values("ts_start").to_dict("records"):
        groups.setdefault((path_of(r["row"]), r["flagged"]), []).append(r)
    rep_of_path: dict[tuple, str] = {}
    reps = []
    for (p, is_flag), rs in groups.items():
        rep = max(rs, key=lambda x: (x["excess_ms"], np.nan_to_num(x["own_z"], nan=-1e9)))
        reps.append((p, is_flag, rs, rep))
        if p not in rep_of_path or is_flag:
            rep_of_path[p] = rep["span_id"]
    nodes, flagged = [], []
    for p, is_flag, rs, rep in reps:
        node = {
            "span_id": rep["span_id"], "parent": rep_of_path.get(p[:-1]) if len(p) > 1 else None, "service": rep["service"],
            "operation": str(rep["operation"])[:70], "dur_ms": fnum(rep["duration_ms"], 2), "own_ms": fnum(rep["own_ms"], 2),
            "own_z": fnum(rep["own_z"]), "gap_ms": fnum(rep["edge_gap_ms"], 2), "gap_z": fnum(rep["gap_z"]),
            "status": "error" if rep["status"] > 0 else "ok", "flagged": bool(is_flag), "reasons": rep["reasons"],
        }
        if isinstance(rep["callee"], str):
            node["unobserved_callee"] = rep["callee"]
        if is_flag:
            node["op_shift"] = fnum(rep["gap_shift"] if "edge_gap" in rep["reasons"] else rep["own_shift"])
        if len(rs) > 1:
            node["repeated"] = len(rs)
        nodes.append(node)
        if is_flag:
            bs = blamed_services(rep)
            flagged.append({**node, "blamed_services": bs, "blamed_service": bs[0] if bs else rep["service"],
                            "caller_service": rep["caller_service"], "trace_id": trace_id, "depth": len(p)})
    pruned = t[~t["row"].isin(keep)]
    root = t[t["is_root"]].iloc[0] if t["is_root"].any() else t.iloc[0]
    return {
        "trace_id": trace_id, "entry_service": root["service"], "entry_operation": str(root["operation"])[:70],
        "duration_ms": round(float(root["duration_ms"]), 2), "n_spans": int(len(t)),
        "spans": nodes, "pruned_normal_spans": int(len(pruned)),
        "pruned_by_service": pruned.groupby("service").size().sort_values(ascending=False).head(12).to_dict(),
        "flagged": flagged,
    }

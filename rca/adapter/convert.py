"""Convert one raw RCAEval case into the canonical schema (SPEC Section 5).

Output folder data/canonical/<dataset>/<case_id>/:
  case.json, truth.json, metrics.parquet, logs.parquet, templates.parquet,
  spans.parquet, entities.parquet, convert_report.json
Missing modalities are recorded in case.json (has_* = false) and no file is written.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from rca.adapter.layout import case_id_for, parse_folder
from rca.paths import CANONICAL_DIR, system_config
from rca.scoring import indicator_for

LEVEL_RE = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|SEVERE|FATAL|CRITICAL)\b", re.I)
STACK_RE = re.compile(r"(Exception|Traceback|\tat [\w.$]+\(|^\s+at [\w.$]+\(|panic:|goroutine \d+|Error:)", re.M)


# ------------------------------------------------------------------ names
def normalise(name: str) -> str:
    n = re.sub(r"[^a-z0-9]", "", str(name).lower())
    for suf in system_config()["adapter"]["name_normalise"]["strip_suffixes"]:
        if n.endswith(suf) and len(n) > len(suf):
            n = n[: -len(suf)]
    return n


def build_name_map(raw_names, entities) -> tuple[dict, list]:
    """Map raw (trace/log) service names onto metric entities: exact, then normalised."""
    ents = sorted(set(entities))
    by_norm: dict[str, list[str]] = {}
    for e in ents:
        by_norm.setdefault(normalise(e), []).append(e)
    mapping, unmatched = {}, []
    for r in sorted(set(map(str, raw_names))):
        if r in ents:
            mapping[r] = r
        elif len(by_norm.get(normalise(r), [])) == 1:
            mapping[r] = by_norm[normalise(r)][0]
        else:
            mapping[r] = r
            unmatched.append(r)
    return mapping, unmatched


def metric_type(metric: str) -> str:
    for rule in system_config()["metric_types"]:
        if re.search(rule["regex"], metric, re.I):
            return rule["type"]
    return "other"


# ------------------------------------------------------------------ metrics
def _wide_to_long(df: pd.DataFrame, source: str) -> pd.DataFrame:
    cfg = system_config()["adapter"]
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[[c for c in df.columns if c == "time" or not str(c).startswith("time")]]
    t = pd.to_numeric(df["time"], errors="coerce")
    df = df.loc[t.notna()].copy()
    df["time"] = t[t.notna()].astype(np.int64)
    df = df.sort_values("time").drop_duplicates("time")
    drop = re.compile(cfg["drop_metric_regex"])
    counter = re.compile(cfg["counter_suffix_regex"])
    frames = []
    for c in df.columns:
        if c == "time" or "_" not in c or drop.search(c):
            continue
        entity, metric = c.split(cfg["metric_column_split"], 1)
        v = pd.to_numeric(df[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if counter.search(metric):
            dv = v.diff() / df["time"].diff()
            v = dv.where(dv >= 0)
        frames.append(pd.DataFrame({"ts": df["time"].values, "entity": entity, "metric": metric,
                                    "value": v.values.astype(np.float32), "source": source}))
    if not frames:
        return pd.DataFrame(columns=["ts", "entity", "metric", "value", "source"])
    return pd.concat(frames, ignore_index=True)


def read_metrics(case_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    used, parts = [], []
    # derived service-level metrics first (their short names are the indicator vocabulary)
    for name, src in [("simple_metrics.csv", "derived"), ("simple_data.csv", "derived"),
                      ("metrics.csv", "raw"), ("data.csv", "raw")]:
        p = case_dir / name
        if p.exists():
            parts.append(_wide_to_long(pd.read_csv(p, low_memory=False), src))
            used.append(name)
    m = pd.concat(parts, ignore_index=True)
    m = m.drop_duplicates(["ts", "entity", "metric"], keep="first")
    return m, used


# ------------------------------------------------------------------ entities
def read_entities(case_dir: Path, logs: pd.DataFrame | None, metric_entities: set[str]) -> pd.DataFrame:
    rx = re.compile(system_config()["adapter"]["pod_service_regex"])
    rows = []
    for p in sorted(case_dir.glob("pod-node-*.csv")):
        d = pd.read_csv(p)
        for _, r in d.iterrows():
            rows.append({"pod": str(r.iloc[0]), "node": str(r.iloc[1])})
    if logs is not None and "pod_raw" in logs and "node_raw" in logs:
        pn = logs[["pod_raw", "node_raw"]].dropna().drop_duplicates()
        rows += [{"pod": a, "node": b} for a, b in pn.itertuples(index=False)]
    ent = pd.DataFrame(rows, columns=["pod", "node"]).drop_duplicates("pod")
    services = []
    for pod in ent["pod"]:
        m = rx.match(pod)
        services.append(m["service"] if m else pod)
    ent["service"] = services
    nodes = set(ent["node"].dropna())
    # services seen only in metrics (no pod information) get one row with unknown pod/node
    known = set(ent["service"])
    extra = sorted(e for e in metric_entities if e not in known and e not in nodes)
    ent = pd.concat([ent, pd.DataFrame({"pod": [None] * len(extra), "node": [None] * len(extra), "service": extra})],
                    ignore_index=True)
    return ent[["pod", "service", "node"]]


# ------------------------------------------------------------------ logs
def read_logs(case_dir: Path) -> pd.DataFrame | None:
    p = case_dir / "logs.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""], low_memory=False)
    if d.empty:
        return None
    ts = pd.to_numeric(d["timestamp"], errors="coerce") / 1e9
    out = pd.DataFrame({"ts": ts, "service_raw": d["container_name"], "message": d["message"].fillna("")})
    if "level" in d:
        lvl = d["level"].fillna("").str.upper()
    else:
        lvl = pd.Series("", index=d.index)
    parsed = out["message"].str.extract(LEVEL_RE, expand=False).fillna("").str.upper()
    out["level"] = lvl.where(lvl != "", parsed).replace({"WARNING": "WARN", "SEVERE": "ERROR", "CRITICAL": "FATAL"})
    out["pod_raw"] = d["pod_name"] if "pod_name" in d else None
    out["node_raw"] = d["node_name"] if "node_name" in d else None
    return out[out["ts"].notna()].sort_values("ts").reset_index(drop=True)


_MASKS = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<UUID>"),
    (re.compile(r"\b[0-9a-f]{16,}\b", re.I), "<HEX>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?Z?"), "<TS>"),
    (re.compile(r"\b\d+(\.\d+)?(ms|µs|us|s)?\b"), "<NUM>"),
]


def _mask(msg: str) -> str:
    for rx, tok in _MASKS:
        msg = rx.sub(tok, msg)
    return msg[:2000]


def template_logs(logs: pd.DataFrame, baseline_end: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drain3 fitted on baseline-window messages first; later messages either match a baseline
    template or form new ones (in_baseline = False). Runs per service so templates never mix services."""
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig

    cfg = system_config()["adapter"]["drain"]
    tcfg = TemplateMinerConfig()
    tcfg.drain_sim_th = cfg["sim_th"]
    tcfg.drain_depth = cfg["depth"]
    tcfg.drain_max_children = cfg["max_children"]
    tcfg.profiling_enabled = False

    logs = logs.copy()
    logs["masked"] = [_mask(m) for m in logs["message"].values]
    logs["template_id"] = -1
    trows = []
    next_id = 0
    for svc, g in logs.groupby("service", sort=True):
        miner = TemplateMiner(config=tcfg)
        base = g[g["ts"] < baseline_end]["masked"].unique()
        rest = g[g["ts"] >= baseline_end]["masked"].unique()
        cluster_of: dict[str, int] = {}
        for msg in base:
            cluster_of[msg] = miner.add_log_message(msg)["cluster_id"]
        base_clusters = set(cluster_of.values())
        for msg in rest:
            if msg not in cluster_of:
                cluster_of[msg] = miner.add_log_message(msg)["cluster_id"]
        local = {}
        for c in miner.drain.clusters:
            local[c.cluster_id] = next_id
            trows.append({"template_id": next_id, "service": svc, "template": c.get_template()[:500],
                          "in_baseline": c.cluster_id in base_clusters})
            next_id += 1
        logs.loc[g.index, "template_id"] = [local[cluster_of[m]] for m in g["masked"].values]
    templates = pd.DataFrame(trows, columns=["template_id", "service", "template", "in_baseline"])
    return logs.drop(columns=["masked"]), templates


# ------------------------------------------------------------------ traces
def read_spans(case_dir: Path) -> pd.DataFrame | None:
    p = case_dir / "traces.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, dtype={"traceID": str, "spanID": str, "parentSpanID": str, "serviceName": str,
                              "operationName": str, "methodName": str}, low_memory=False)
    if d.empty:
        return None
    start_us = pd.to_numeric(d["startTime"], errors="coerce")
    out = pd.DataFrame({
        "ts_start": start_us / 1e6,
        "duration_ms": pd.to_numeric(d["duration"], errors="coerce") / 1e3,
        "trace_id": d["traceID"],
        "span_id": d["spanID"],
        "parent_span_id": d["parentSpanID"] if "parentSpanID" in d else None,
        "service_raw": d["serviceName"],
        "operation": d["operationName"].fillna(d.get("methodName", "")),
        "status_raw": d["statusCode"] if "statusCode" in d else np.nan,
    })
    code = pd.to_numeric(out["status_raw"], errors="coerce")
    http_min = system_config()["adapter"]["error_status_http_min"]
    # HTTP codes (>= 100) are errors from http_min upward; small integers are gRPC codes (non-zero = error)
    status = np.where(code.isna(), -1, np.where(code >= 100, (code >= http_min).astype(int), (code != 0).astype(int)))
    out["status"] = status.astype(np.int8)
    return out[out["ts_start"].notna()].reset_index(drop=True)


# ------------------------------------------------------------------ case
def convert_case(dataset: str, case_dir: Path, out_root: Path = CANONICAL_DIR, overwrite: bool = False) -> dict:
    case_id = case_id_for(dataset, case_dir)
    out = Path(out_root) / dataset / case_id
    if (out / "convert_report.json").exists() and not overwrite:
        return json.loads((out / "convert_report.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    folder = parse_folder(case_dir.parent.name)
    wcfg = system_config()["window"]
    inject = int(open(case_dir / "inject_time.txt").read().strip())

    # the raw folder name encodes the answer, so it is stored only in truth.json
    report: dict = {"case_id": case_id, "dataset": dataset}

    metrics, used = read_metrics(case_dir)
    metric_entities = set(metrics["entity"].unique())
    logs = read_logs(case_dir)
    spans = read_spans(case_dir)
    entities = read_entities(case_dir, logs, metric_entities)
    nodes = set(entities["node"].dropna())
    service_entities = sorted(metric_entities - nodes)

    metrics["entity_level"] = np.where(metrics["entity"].isin(nodes), "node", "service")
    metrics["metric_type"] = metrics["metric"].map({m: metric_type(m) for m in metrics["metric"].unique()})
    metrics = metrics[["ts", "entity", "entity_level", "metric", "metric_type", "value", "source"]]
    metrics.to_parquet(out / "metrics.parquet", index=False)
    report["metric_files"] = used
    report["metric_rows"] = len(metrics)
    report["metric_channels"] = int(metrics.groupby(["entity", "metric"]).ngroups)

    t_min, t_max = int(metrics["ts"].min()), int(metrics["ts"].max())
    case = {
        "case_id": case_id, "dataset": dataset, "system": dataset.split("-")[1],
        "fault_start": inject,
        "baseline_start": max(t_min, inject - wcfg["baseline_seconds"]), "baseline_end": inject,
        "window_start": inject, "window_end": min(t_max, inject + wcfg["analysis_seconds"]),
        "data_start": t_min, "data_end": t_max,
        "has_metrics": True, "has_logs": logs is not None, "has_traces": spans is not None,
    }

    if logs is not None:
        lmap, unmatched = build_name_map(logs["service_raw"].unique(), service_entities)
        logs["service"] = logs["service_raw"].map(lmap)
        logs["pod"] = logs["pod_raw"] if logs["pod_raw"].notna().any() else None
        logs, templates = template_logs(logs, case["baseline_end"])
        logs[["ts", "service", "pod", "level", "message", "template_id"]].to_parquet(out / "logs.parquet", index=False)
        templates.to_parquet(out / "templates.parquet", index=False)
        report.update(log_rows=len(logs), log_templates=len(templates),
                      log_new_templates=int((~templates["in_baseline"]).sum()), log_unmatched_services=unmatched)

    if spans is not None:
        smap, unmatched = build_name_map(spans["service_raw"].unique(), service_entities)
        spans["service"] = spans["service_raw"].map(smap)
        spans["pod"] = None
        has_parent = spans["parent_span_id"].notna().any()
        report.update(span_rows=len(spans), trace_count=int(spans["trace_id"].nunique()),
                      span_unmatched_services=unmatched, span_service_map={k: v for k, v in smap.items() if k != v},
                      has_parent_field=bool(has_parent))
        spans[["ts_start", "duration_ms", "trace_id", "span_id", "parent_span_id", "service", "service_raw", "pod",
               "operation", "status", "status_raw"]].astype({"status_raw": str}).to_parquet(out / "spans.parquet", index=False)

    entities.to_parquet(out / "entities.parquet", index=False)
    report["entities"] = {"services": len(service_entities), "pods": int(entities["pod"].notna().sum()), "nodes": len(nodes)}

    truth = {"gt_service": folder["service"], "gt_fault_type": folder["fault"],
             "gt_indicator": indicator_for(folder["fault"], dataset), "folder_variant": folder["variant"],
             "raw_folder": f"{case_dir.parent.name}/{case_dir.name}",
             "gt_in_entities": folder["service"] in service_entities}
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    (out / "case.json").write_text(json.dumps(case, indent=1))
    report["ok"] = True
    (out / "convert_report.json").write_text(json.dumps(report, indent=1, default=str))
    return report

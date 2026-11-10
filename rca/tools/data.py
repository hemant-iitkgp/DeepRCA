"""Canonical case reader used by every code tool and the control.

It opens only the canonical telemetry files of one case. truth.json is never readable
through it (see `_ALLOWED`), and nothing under rca/tools imports rca.truth.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

import pandas as pd

from rca.paths import CANONICAL_DIR, system_config

_ALLOWED = {"case.json", "metrics.parquet", "logs.parquet", "templates.parquet", "spans.parquet", "entities.parquet"}


class CaseData:
    """Lazy, cached access to one canonical case."""

    def __init__(self, dataset: str, case_id: str, root: Path | None = None, rename: dict | None = None,
                 hide_traces: bool = False):
        self.dataset = dataset
        self.case_id = case_id
        self.dir = Path(root or CANONICAL_DIR) / dataset / case_id
        # optional service renaming (the `anonymize` switch): real name -> alias
        self.rename = rename or {}
        # the `traces: off` switch: behave as if the case had no traces (no-trace path on any case)
        self.hide_traces = hide_traces

    @property
    def cache_key(self) -> str:
        """Cache folder for this case; renamed (anonymised) views get their own."""
        return f"{self.dataset}/{self.case_id}" + ("-anon" if self.rename else "")

    def _path(self, name: str) -> Path:
        if name not in _ALLOWED:
            raise PermissionError(f"{name} is not readable by tools")
        return self.dir / name

    def _ren(self, df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        if self.rename:
            for c in cols:
                if c in df:
                    df[c] = df[c].map(lambda v: self.rename.get(v, v))
            if "pod" in df:
                df["pod"] = df["pod"].map(self._anon_pod)
            if "operation" in df:
                ops = {o: self._anon_text(o) for o in df["operation"].dropna().unique()}
                df["operation"] = df["operation"].map(lambda o: ops.get(o, o))
        return df

    def _anon_pod(self, pod):
        if not isinstance(pod, str):
            return pod
        for real in sorted(self.rename, key=len, reverse=True):
            if pod.startswith(real + "-"):
                return self.rename[real] + pod[len(real):]
        return pod

    def _anon_text(self, text: str) -> str:
        """Replace tokens that name a service (same normalisation as the callee matcher) with its alias."""
        import re

        from rca.tools.traces import _common_prefix, _norm

        if not hasattr(self, "_stems"):
            prefix = _common_prefix(list(self.rename))
            self._stems = {_norm(r, prefix): a for r, a in self.rename.items() if len(_norm(r, prefix)) >= 2}
            self._prefix = prefix
        out = []
        for tok in re.split(r"([^A-Za-z0-9-]+)", str(text)):
            alias = self._stems.get(_norm(tok, self._prefix)) if tok and tok[0].isalnum() else None
            out.append(alias if alias else tok)
        return "".join(out)

    @functools.cached_property
    def case(self) -> dict:
        c = json.loads(self._path("case.json").read_text())
        if self.hide_traces:
            c["has_traces"] = False
        return c

    @functools.cached_property
    def metrics(self) -> pd.DataFrame:
        m = pd.read_parquet(self._path("metrics.parquet"))
        rx = system_config()["adapter"]["node_entity_regex"]
        hosts = [e for e in m["entity"].unique() if re.match(rx, str(e))]
        if hosts:
            m.loc[m["entity"].isin(hosts), "entity_level"] = "node"
        return self._ren(m, ["entity"])

    def _anon_col(self, df: pd.DataFrame, col: str) -> pd.DataFrame:
        if self.rename and col in df:
            m = {v: self._anon_text(v) for v in df[col].dropna().unique()}
            df[col] = df[col].map(lambda v: m.get(v, v))
        return df

    @functools.cached_property
    def logs(self) -> pd.DataFrame | None:
        if not self.case["has_logs"]:
            return None
        return self._anon_col(self._ren(pd.read_parquet(self._path("logs.parquet")), ["service"]), "message")

    @functools.cached_property
    def templates(self) -> pd.DataFrame | None:
        if not self.case["has_logs"]:
            return None
        return self._anon_col(self._ren(pd.read_parquet(self._path("templates.parquet")), ["service"]), "template")

    @functools.cached_property
    def spans(self) -> pd.DataFrame | None:
        if not self.case["has_traces"]:
            return None
        s = pd.read_parquet(self._path("spans.parquet"))
        # the raw (pre-mapping) service name is adapter bookkeeping, not evidence
        return self._ren(s.drop(columns=["service_raw"], errors="ignore"), ["service"])

    @functools.cached_property
    def entities(self) -> pd.DataFrame:
        return self._ren(pd.read_parquet(self._path("entities.parquet")), ["service"])

    @functools.cached_property
    def services(self) -> list[str]:
        """Candidate services: entities with service-level metrics (nodes excluded)."""
        m = self.metrics
        return sorted(m.loc[m["entity_level"] == "service", "entity"].unique())

    # windows -----------------------------------------------------------------
    @property
    def fault_start(self) -> float:
        return self.case["fault_start"]

    def baseline(self) -> tuple[float, float]:
        return self.case["baseline_start"], self.case["baseline_end"]

    def window(self) -> tuple[float, float]:
        return self.case["window_start"], self.case["window_end"]

"""Per-case run state: flagged work items, frontier, evidence files, provenance, limits.

Coverage is enforced here in code (SPEC 3.4 rule 4): every flagged work item needs a finding
file, `next_frontier` lists what is still uncovered, and `candidate_rank` stays locked until the
frontier is empty.
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from pathlib import Path

from rca.tools.data import CaseData

EVIDENCE = "evidence"


class LimitHit(Exception):
    pass


class RunState:
    def __init__(self, cd: CaseData, workdir: Path, limits: dict, variant: dict):
        self.cd = cd
        self.workdir = Path(workdir)
        self.files = self.workdir / "files"
        (self.files / EVIDENCE).mkdir(parents=True, exist_ok=True)
        (self.files / "report").mkdir(parents=True, exist_ok=True)
        self.limits = limits
        self.variant = variant
        self.lock = threading.RLock()
        self.items: dict[str, dict] = {}          # work item id -> info (flagged span or anomalous service)
        self.item_keys: dict[tuple, str] = {}     # dedupe key -> item id
        self.duplicates: Counter = Counter()
        self.selected_traces: list[dict] = []
        self.trees: dict[str, dict] = {}
        self.frontier_empty_seen = False
        self.candidate_rank_called = False
        self.launches: list[dict] = []
        self.rejections: list[dict] = []
        self.limits_hit: list[str] = []
        self.provenance: list[dict] = []
        self.running_top: str | None = None
        self.hyp_counter = 0
        self.t_start = time.time()
        self.tokens = 0
        self.final_report: dict | None = None
        self.submit_attempts = 0

    # ------------------------------------------------------------------ work items
    def register_flagged(self, trace_id: str, flagged: list[dict]) -> list[str]:
        """Register flagged spans from a trace tree; identical (service, operation, blamed service, reason)
        spans seen in several traces become one work item."""
        ids = []
        with self.lock:
            for f in flagged:
                key = ("span", f["service"], f["operation"], f.get("blamed_service"), tuple(sorted(f["reasons"])))
                if key in self.item_keys:
                    self.duplicates[self.item_keys[key]] += 1
                    ids.append(self.item_keys[key])
                    continue
                iid = f["span_id"]
                self.item_keys[key] = iid
                self.items[iid] = {"kind": "span", "id": iid, "depth": f.get("depth", 1), "trace_id": trace_id,
                                   "source": "trace_tree", **f}
                ids.append(iid)
        return ids

    def register_service_items(self, services: list[dict]) -> list[str]:
        with self.lock:
            ids = []
            for i, s in enumerate(services):
                iid = "svc-" + s["service"]
                if iid not in self.items:
                    # one level, investigated in parallel; `order` keeps the deepest-callee-first listing
                    # (part1-frozen-v2: depth i+1 had made them run one after another)
                    self.items[iid] = {"kind": "service", "id": iid, "depth": 1, "order": i, "service": s["service"],
                                       "blamed_service": s["service"], "source": "metric_anomalies", **s}
                ids.append(iid)
            return ids

    def register_expansion(self, span_id: str, requested_by: str) -> dict | None:
        """A child span an investigator asked to expand becomes a work item (if it exists in the case)."""
        with self.lock:
            if span_id in self.items:
                return self.items[span_id]
            from rca.tools.traces import span_table

            st = span_table(self.cd)
            hit = st[st["span_id"] == span_id]
            if hit.empty:
                return None
            r = hit.iloc[0]
            parent_depth = self.items.get(requested_by, {}).get("depth", 1)
            self.items[span_id] = {"kind": "span", "id": span_id, "depth": parent_depth + 1, "trace_id": r["trace_id"],
                                   "service": r["service"], "operation": str(r["operation"])[:70],
                                   "blamed_service": r["callee"] if isinstance(r["callee"], str) else r["service"],
                                   "reasons": ["expansion_requested"], "source": f"expand:{requested_by}"}
            return self.items[span_id]

    def finding_path(self, iid: str) -> Path:
        return self.files / EVIDENCE / f"span_{iid}.json"

    def findings(self) -> dict[str, dict]:
        out = {}
        for p in sorted((self.files / EVIDENCE).glob("span_*.json")):
            try:
                out[p.stem[5:]] = json.loads(p.read_text())
            except Exception:
                continue
        return out

    def hypotheses(self) -> list[dict]:
        out = []
        for p in sorted((self.files / EVIDENCE).glob("hyp_*.json")):
            try:
                out.append(json.loads(p.read_text()))
            except Exception:
                continue
        return out

    def critic(self) -> dict | None:
        p = self.files / EVIDENCE / "critic.json"
        return json.loads(p.read_text()) if p.exists() else None

    def uncovered(self) -> list[dict]:
        """Work items without a finding file, plus expansion requests found in findings."""
        with self.lock:
            fs = self.findings()
            for iid, f in fs.items():
                for child in f.get("expand_next", []) or []:
                    self.register_expansion(str(child), iid)
            fs = self.findings()
            return [it for iid, it in self.items.items() if iid not in fs]

    def next_frontier(self) -> list[dict]:
        unc = self.uncovered()
        if not unc:
            self.frontier_empty_seen = True
            return []
        d = min(it["depth"] for it in unc)
        return sorted([it for it in unc if it["depth"] == d], key=lambda x: (x.get("order", 0), x["id"]))

    # ------------------------------------------------------------------ limits
    def check_limits(self) -> None:
        if time.time() - self.t_start > self.limits["wall_clock_seconds"]:
            self._hit("wall_clock")
        if self.tokens > self.limits["max_tokens_per_case"]:
            self._hit("max_tokens_per_case")

    def _hit(self, name: str) -> None:
        if name not in self.limits_hit:
            self.limits_hit.append(name)
        raise LimitHit(name)

    # ------------------------------------------------------------------ provenance
    def note(self, component: str, event: str, top: str | None = None, **extra) -> None:
        with self.lock:
            rec = {"t": round(time.time() - self.t_start, 2), "component": component, "event": event}
            if top is not None and top != self.running_top:
                rec["top_changed"] = {"from": self.running_top, "to": top}
                self.running_top = top
            rec["running_top"] = self.running_top
            rec.update(extra)
            self.provenance.append(rec)

    def evidence_top(self) -> str | None:
        """Running top candidate from findings so far (code-computed support, see guardrails.support)."""
        from rca.guardrails.support import support_scores

        sc = support_scores(self)
        return max(sc, key=lambda s: (sc[s], s)) if sc else None

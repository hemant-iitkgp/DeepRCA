"""C4: are the numbers the agents quote faithful to the data? (SPEC 10, theme C; OmniRCA: 43 of 43 values true,
7 of 8 "z-scores" mislabelled)

Every numeric claim in the evidence_for items of every finding is checked against code recomputation:
  own_time / edge_gap items   every "<number> ms" must be within 5% (or 0.5 ms) of the work item's own time, gap or
                              duration, or of a child span's own time, gap or duration (from the case's span table)
  metric items                every z value ("z 537", "z-score 31.5", "z=3.9") must be within 5% of the peak |z| of
                              some anomalous metric of a service named in the item or of the finding's service,
                              recomputed by rca.tools.metrics.entity_anomalies (z above 100 is shown capped at 100)
Each item is "verified" (all its numbers match), "mismatch" (some number matches nothing), or "unchecked" (no number
of that kind). Mismatches are listed for inspection.

Writes results/p2_c4_items.csv and results/p2_c4_summary.csv.
Usage: python analysis/p2_c4_faithfulness.py [--tag w12_r1]
"""
from __future__ import annotations

import argparse
import re

import pandas as pd

from p2_common import findings, load_cases, provenance, save
from rca.guardrails.support import ev_items
from rca.tools.data import CaseData
from rca.tools.metrics import entity_anomalies

MS_RX = re.compile(r"(\d+(?:\.\d+)?)\s*ms\b")
Z_RX = re.compile(r"\bz(?:[-_ ]?score)?\s*(?:of|=|:)?\s*(-?\d+(?:\.\d+)?)", re.I)


def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.05 * abs(b), 0.5)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w12_r1")
    args = ap.parse_args()
    d = load_cases(args.tag)
    rows = []
    for r in d.itertuples():
        fs = findings(r.run_dir)
        if not fs:
            continue
        cd = CaseData(r.dataset, r.case_id)
        w0, w1 = cd.window()
        services = set(cd.services)
        items = {it["id"]: it for it in provenance(r.run_dir).get("work_items", [])}
        st = None
        zcache: dict[str, list[float]] = {}

        def zs(ent: str) -> list[float]:
            if ent not in zcache:
                zcache[ent] = [a["peak_z"] for a in entity_anomalies(cd, ent, w0, w1, 3.0)]
            return zcache[ent]

        for f in fs:
            it = items.get(f.get("span_id"), {})
            for e in ev_items(f.get("evidence_for")):
                typ, text = e.get("type"), f"{e.get('detail', '')} {e.get('value', '')}"
                if typ in ("own_time", "edge_gap"):
                    nums = [float(x) for x in MS_RX.findall(text)]
                    if not nums:
                        rows.append({"case_id": r.case_id, "type": typ, "status": "unchecked", "text": text[:160]})
                        continue
                    ref = [v for v in (it.get("own_ms"), it.get("gap_ms"), it.get("dur_ms")) if isinstance(v, (int, float))]
                    if it.get("kind") == "span" and cd.case["has_traces"]:
                        if st is None:
                            from rca.tools.traces import span_table
                            st = span_table(cd)
                        row = st[st["span_id"] == it["id"]]
                        if not row.empty:
                            kids = st[st["parent_row"] == row.iloc[0]["row"]]
                            ref += [float(x) for x in pd.concat([kids["own_ms"], kids["duration_ms"],
                                                                 kids["edge_gap_ms"].dropna()]).tolist()]
                            ref += [float(row.iloc[0]["own_ms"]), float(row.iloc[0]["duration_ms"])]
                    ok = all(any(close(n, v) for v in ref) for n in nums)
                    rows.append({"case_id": r.case_id, "type": typ, "status": "verified" if ok else "mismatch", "text": text[:160]})
                elif typ == "metric":
                    nums = [abs(float(x)) for x in Z_RX.findall(text)]
                    if not nums:
                        rows.append({"case_id": r.case_id, "type": typ, "status": "unchecked", "text": text[:160]})
                        continue
                    ents = {s for s in services if re.search(rf"\b{re.escape(s)}\b", text)} | {f.get("service")}
                    ref = [z for ent in ents if ent for z in zs(ent)]
                    ref += [min(z, 100.0) for z in ref]
                    ok = all(any(close(n, v) for v in ref) for n in nums)
                    rows.append({"case_id": r.case_id, "type": typ, "status": "verified" if ok else "mismatch", "text": text[:160]})
    it = pd.DataFrame(rows)
    save(it, "p2_c4_items.csv")
    s = it.groupby(["type", "status"]).size().rename("n").reset_index()
    s["share_of_type"] = s["n"] / s.groupby("type")["n"].transform("sum")
    checked = it[it["status"] != "unchecked"]
    s = pd.concat([s, pd.DataFrame([{"type": "ALL checked", "status": "verified",
                                     "n": int((checked["status"] == "verified").sum()),
                                     "share_of_type": (checked["status"] == "verified").mean()}])], ignore_index=True)
    save(s, "p2_c4_summary.csv")
    pd.set_option("display.width", 200)
    print(s.round(3).to_string(index=False))
    print(it[it["status"] == "mismatch"].head(12).to_string(index=False))


if __name__ == "__main__":
    main()

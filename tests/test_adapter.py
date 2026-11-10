"""Phase 1: canonical data matches the raw data (row counts), on two cases per dataset."""
import csv
import json

import pandas as pd
import pytest

from rca.adapter.layout import case_id_for, list_raw_cases
from rca.paths import CANONICAL_DIR, DATASETS, RAW_DIR


def _rows(path):
    with open(path, "rb") as f:
        return sum(1 for _ in f) - 1


def cases(ds, n=2):
    if not (RAW_DIR / ds).exists():
        return []
    raw, _ = list_raw_cases(ds)
    return [(c, case_id_for(ds, c)) for c in raw[:: max(1, len(raw) // n)][:n]]


@pytest.mark.parametrize("ds", DATASETS)
def test_counts_match_raw(ds):
    for raw, cid in cases(ds):
        out = CANONICAL_DIR / ds / cid
        if not (out / "case.json").exists():
            pytest.skip("not converted")
        case = json.loads((out / "case.json").read_text())
        assert case["fault_start"] == int((raw / "inject_time.txt").read_text().strip())
        assert case["has_traces"] == (raw / "traces.csv").exists()
        assert case["has_logs"] == (raw / "logs.csv").exists()
        if case["has_traces"]:
            raw_spans = pd.read_csv(raw / "traces.csv", usecols=["traceID", "spanID", "startTime"])
            raw_n = int(pd.to_numeric(raw_spans["startTime"], errors="coerce").notna().sum())
            assert len(pd.read_parquet(out / "spans.parquet", columns=["span_id"])) == raw_n
        if case["has_logs"]:
            raw_logs = pd.read_csv(raw / "logs.csv", usecols=["timestamp"], dtype=str)
            raw_n = int(pd.to_numeric(raw_logs["timestamp"], errors="coerce").notna().sum())
            assert len(pd.read_parquet(out / "logs.parquet", columns=["ts"])) == raw_n
        # every raw metric column (except configured drops) is a canonical channel
        m = pd.read_parquet(out / "metrics.parquet", columns=["entity", "metric"]).drop_duplicates()
        chans = set(m["entity"] + "_" + m["metric"])
        for name in ("simple_metrics.csv", "simple_data.csv", "metrics.csv", "data.csv"):
            if (raw / name).exists():
                with open(raw / name) as f:
                    cols = next(csv.reader(f))
                kept = [c for c in cols if "_" in c and not c.startswith("time")
                        and not any(k in c for k in ("spec-cpu-quota", "spec-memory-limit-bytes"))
                        and not c.endswith("latency-50")]
                assert set(kept) <= chans, f"{name}: {sorted(set(kept) - chans)[:5]}"


def test_all_cases_converted():
    sp = pd.read_csv(CANONICAL_DIR.parent / "splits.csv")
    missing = [c for d, c in zip(sp["dataset"], sp["case_id"]) if not (CANONICAL_DIR / d / c / "case.json").exists()]
    assert not missing, f"{len(missing)} cases not converted"
    assert len(sp) == 735

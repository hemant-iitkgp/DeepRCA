# Data audit (Phase 0)

What the RCAEval data actually contains, checked file by file, and where it differs from what SPEC Section 2.1 assumed. Every number below comes from `analysis/audit_data.py` and is read from the CSV named next to it.

Source: Zenodo record 14590730, the nine zips RCAEval's own download functions use. All nine match Zenodo's md5 checksums (server log `~/deeprca-data/raw/fetch.log`). RCAEval code: commit `2fca61b`, package version 1.8.1.

## 1. Cases per dataset

Source: `results/audit_summary.csv`.

| Dataset | Cases | Injected services | Fault labels | Pre-fault data, median (min) | Size per case, median (MB) | Total (MB) |
|---|---|---|---|---|---|---|
| RE1-OB | 125 | 5 | cpu, delay, disk, loss, mem | 6.0 | 0.58 | 175.0 |
| RE1-SS | 125 | 5 | cpu, delay, disk, loss, mem | 6.0 | 4.1 | 507.6 |
| RE1-TT | 125 | 5 | cpu, delay, disk, loss, mem | 8.0 | 15.06 | 1881.0 |
| RE2-OB | 90 | 5 | cpu, delay, disk, loss, mem, socket | 12.0 | 97.9 | 8553.2 |
| RE2-SS | 90 | 5 | cpu, delay, disk, loss, mem, socket | 12.0 | 25.6 | 2323.1 |
| RE2-TT | 90 | 5 | cpu, delay, disk, loss, mem, socket | 12.0 | 271.9 | 23334.4 |
| RE3-OB | 30 | 4 | f1 to f5 | 12.0 | 48.5 | 1427.9 |
| RE3-SS | 30 | 3 | f1 to f4 | 12.0 | 32.8 | 934.9 |
| RE3-TT | 30 | 2 | f1 to f4 | 15.0 | 74.8 | 2220.2 |

Total: 735 cases, matching the paper. Pre-fault minutes: one RE1-OB case has 35 minutes, all others 6 (`results/audit_cases.csv`, column `pre_fault_min`). Post-fault length equals pre-fault length in every dataset.

## 2. Modalities per dataset

Source: `results/audit_summary.csv`; trace and log row counts from `results/audit_cases.csv`.

| Dataset | Metrics | Logs | Traces (non-empty) | Parent-span field | Metric columns (min to max) |
|---|---|---|---|---|---|
| RE1-OB | 125 | 0 | 0 | none | 50 to 59 |
| RE1-SS | 125 | 0 | 0 | none | 420 to 438 |
| RE1-TT | 125 | 0 | 0 | none | 1179 to 1445 |
| RE2-OB | 90 | 90 | 90 | 90 | 401 to 461 |
| RE2-SS | 90 | 90 | **0** | none | 433 to 452 |
| RE2-TT | 90 | 90 | 90 | 90 | 1509 to 1581 |
| RE3-OB | 30 | 30 | 30 | 30 | 388 to 521 |
| RE3-SS | 30 | 30 | **0** (13 empty files) | none | 437 to 550 |
| RE3-TT | 30 | 30 | 30 | 30 | 1300 to 1376 |

## 3. Files, columns, units

Sources: `results/audit_columns.csv` for full column lists, `results/audit_cases.csv` for units.

- **RE1:** one wide metrics file per case: `data.csv`, plus `simple_data.csv` in RE1-SS and RE1-TT. RE1-OB has short metric names (`<service>_cpu`, `_mem`, `_load`, `_latency`, `_error`). RE1-SS and RE1-TT have raw container and istio metric names, such as `<service>_container-cpu-usage-seconds-total`.
- **RE2 and RE3:**
  - `metrics.csv`: raw container, istio and node metrics.
  - `simple_metrics.csv`: RCAEval's derived service-level metrics (cpu, mem, diskio, socket, workload, error, latency-50, latency-90).
  - `logs.csv`, `traces.csv`.
  - RE2 also has `pod-node-1.csv` and `pod-node-2.csv`, plus RCAEval's preprocessed `logts.csv`, `tracets_err.csv` and `tracets_lat.csv`.
- **Time units:**
  - Metric timestamps are unix seconds, sampled every 1 s in all nine datasets.
  - Log `timestamp` is in nanoseconds.
  - Trace `startTime` and `duration` are in microseconds.
  - `inject_time.txt` is unix seconds.
- **Columns:**
  - Logs: `time, timestamp, container_name, message, level, req_path, error` in RE2. RE3 replaces `level`, `req_path` and `error` with `pod_name, node_name`. Some RE2-OB cases also carry `cluster_id, log_template`.
  - Traces: `time, traceID, spanID, serviceName, methodName, operationName, startTimeMillis, startTime, duration, statusCode, parentSpanID`.
- **Logs have no span ID** in any dataset (`log_has_span_id` is false throughout), as the paper says.
- **Status codes:** trace `statusCode` is almost always 0 or empty. A few gRPC codes (2, 4, 12, 13, 14) and an HTTP 400 appear in OB cases; TT status is empty (`trace_status_values`). Error status is therefore weak evidence in this benchmark.

## 4. Fault time and ground truth

- **Fault time:** `inject_time.txt` in every case, as unix seconds (`cases_with_inject_time` = all). RCAEval's baselines get the metric frame cut to `length*60//2` rows on each side of this time (`main.py`, default `length=20`, so up to 600 one-second rows). The system uses the same window (`config/system.yaml`, `window`).
- **Ground truth:** encoded only in folder names `<service>_<fault>/<repetition>/`. Fault labels map to RCAEval's indicator answers in `main.py`: cpu to cpu, mem to mem, delay and loss to latency, disk to diskio (latency in RE1), socket to socket. The RE3 labels f1 to f5 have no indicator mapping in `main.py`, so RE3 indicator-level accuracy is not defined by RCAEval and is not reported.
- **Extra truth-bearing file:** some RE3-SS cases also contain `root_cause.txt`, which holds the root-cause log line. The adapter never reads it, so no tool or agent can reach it.

## 5. Mismatches with SPEC Section 2.1 and other irregularities

| # | Finding | Effect on the design | Handling |
|---|---|---|---|
| 1 | **Sock Shop has no traces in RE2 or RE3.** RE2-SS has no trace file. RE3-SS has 13 header-only files. SPEC 2.1 assumes traces in all RE2/RE3 datasets. | Sock Shop RE2/RE3 cases (120) cannot use trace evidence, and no call graph can be derived for Sock Shop. | They use the no-trace path of SPEC 7.1 (metrics and logs, investigators per anomalous service). The `topology` tool reports callers and callees as unknown for Sock Shop. The evidence-path check (SPEC 7.6 rule 5) cannot run there and is recorded as skipped. The code-only ceiling covers trace-bearing cases only. |
| 2 | **Parent-span field present** in every non-empty trace file. | No parent reconstruction needed (SPEC Phase 1 task 2). | None needed. A median of 8.5 (RE2-OB) and 12 (RE2-TT) spans per case name a parent outside the file (`trace_parent_missing_in_case`); they are treated as roots. |
| 3 | **Some services report no spans of their own.** In Online Boutique, calls to them appear only as the caller's client span, named after the service. | Slow calls to those services would be invisible if only span service names were used. | The trace tools infer the callee from the operation name. Operation tokens are matched to the case's own entity names, using a general normalisation with no hard-coded names. |
| 4 | **Trace service names differ from metric entity names in RE2-OB** (`frontendservice` in traces, `frontend` in metrics). | Evidence from traces and metrics would not join. | The adapter maps names by exact match, then by normalised match (`results/adapter_report.csv`, `span_service_map`). |
| 5 | **Stray entries next to the case folders.** `RE2-OB/checkoutservice_cpu/` contains a `multi-source-data/` folder, its zip and a `.DS_Store` (`results/audit_stray_files.csv`). | They are not cases. RCAEval's `main.py` also ignores them. | Only numbered repetition folders are cases. |
| 6 | **A folder named `RE3-TT/ts-route-service_f3_1/`** holds 3 more f3 cases of the same service, with different injection times. | RCAEval's `main.py` expects exactly one `_` in the folder name and would fail on this folder. | The folder parser accepts an optional numeric variant. Ground truth is service `ts-route-service`, fault `f3`. |
| 7 | **Host entities among metric entities.** RE1-SS and RE1-TT include node-exporter hosts with IP-shaped names (e.g. `192-168-15-8-9100`), and no pod-to-node file exists in RE1. | They would appear as candidate services. | Entities with IP-address-shaped names are treated as nodes (`node_entity_regex` in `config/system.yaml`). |
| 8 | **Pre-fault data differs by dataset** (6 to 15 minutes; one RE1-OB case has 35). | The baseline length cannot be the same everywhere. | Same rule as RCAEval's baselines: up to 600 s before the fault, or all that exists. |

None of these stops the project. Item 1 changes what can be claimed: for Sock Shop the system is tested without traces, so every Sock Shop result is a no-trace result. Part 1 reports it that way.

## 6. Scorer check

RCAEval's own `main.py` ran end to end with `dummy` (a random ranking) and `baro` on RE2-OB. Re-scoring the same result files with this project's scorer wrapper (`rca/scoring.py`, which calls RCAEval's `Evaluator`) reproduces all 12 per-fault Avg@5 values that `main.py` printed (`results/scorer_check.csv`, column `match`).

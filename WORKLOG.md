# WORKLOG

Dated record of decisions, findings, deviations and failed attempts. Newest entries at the bottom of each day.

---

## 2026-10-24

### Setup decisions (from the user, before Phase 0)

- **Isolation from OmniRCA.** The user asked that this project be built in isolation, with no influence from OmniRCA code or results. No file from OmniRCA is read or imported. **Deviation from SPEC Phase 2:** the control is implemented from the SPEC's own definition (Section 1.3 and Phase 2: rank services by their strongest anomaly z-score against a pre-fault baseline window, threshold z > 2.5 for "anomalous", max over channels), not ported, and the reproduction check against OmniRCA's stored control answers (Phase 2 task 2) is not done. The OmniRCA findings table in SPEC Section 2.2 is used only as written in the SPEC (design constraints).
- **Primary model is gpt-4o-mini, not GPT-4o.** The provided OpenAI key's project lists only `gpt-4o-mini`; a call to `gpt-4o` returned `model_not_found` ("Project ... does not have access to model gpt-4o"). The user chose gpt-4o-mini as the primary for now. **Deviation from SPEC 3.5.** The model is a config value; switching later needs no code change, but any LLM-dependent tuning and runs must be redone (cheapest before the Phase 5 freeze).
- **Budget:** $500 total OpenAI spend for Part 1 (SPEC 3.6 approval threshold).
- **Compute and data:** local disk has about 15 GB free, so data, canonical files, runs and caches live on the institute server (`gpu77`, 48 cores, 125 GB RAM, NFS home with about 2 TB free). Code is edited in the local git repo and pushed to a bare repo on the server; results and reports are copied back.
- **Secrets:** the OpenAI key and server credentials live in `.env` (git-ignored). Never committed.

### Phase 0: environment and data

- RCAEval cloned at `~/src/RCAEval`, commit `2fca61b9730a69c21ef72411844735634dbb010f` (2026-10-20), package version 1.8.1. README recommends Python 3.12; conda env `deeprca` (Python 3.12) created on the server, RCAEval installed with `pip install -e .[default]`.
- Data source: the official Zenodo record 14590730 (the URLs RCAEval's own `download_re*_dataset` functions use), downloaded with curl and verified against Zenodo's md5 checksums. Chosen over the Hugging Face Parquet copy because `main.py` (the reference evaluation) reads the Zenodo layout (`data.csv` / `simple_metrics.csv`, `inject_time.txt`).
- **Finding (README, to be confirmed in the audit):** RE2-SS and RE3-SS have no traces ("N/A"). SPEC 2.1 says RE2/RE3 have metrics, logs and traces. Sock Shop cases in RE2/RE3 therefore use the no-trace path of SPEC 7.1 (metrics and logs, topology-ordered investigation). The SPEC already defines this path, so no design change is needed, but it is flagged in `reports/DATA_AUDIT.md`.

### RCAEval evaluation API (confirmed by reading `main.py` and `RCAEval/benchmark/evaluation.py`)

- `Evaluator(max_k=5)`, `add_case(ranks: list[Node], answer: Node, n_candidates=None)`, `accuracy(k)`, `average(k)`. `Node(entity, metric)` from `RCAEval.classes.graph`; equality on (entity, metric).
- Service level (`main.py`): each ranked string is cut at the first `_` and `-db` is stripped, duplicates are removed keeping the first, and every node uses metric `"unknown"`; answer is `Node(gt_service, "unknown")`.
- Indicator level: ranked strings are `service_metric`; answer is `Node(gt_service, indicator)` where cpu→`cpu`, mem→`mem`, delay→`latency`, loss→`latency`, disk→`diskio` (RE2/RE3) or `latency` (RE1), socket→`socket`. **RE3 faults f1 to f5 have no indicator mapping in `main.py`**, so RE3 indicator-level results are not defined by RCAEval; they are not reported.
- Fault time: `inject_time.txt` (unix seconds). Baselines get the metric frame cut to `length*60//2` rows before and after the injection time (default `length=20`).
- Ground truth: encoded in the directory names `<service>_<fault>/<repetition>/`.

### Environment (Phase 0)

- Conda env `deeprca`, Python 3.12, on the server. RCAEval 1.8.1 installed editable with `[default]` (brings numpy 1.26.4, pandas 3.0.6, scikit-learn 1.7.2, torch 2.8.0). Agent stack: deepagents 0.7.26 (pinned to a release more than a week old; 0.7.31 is current), langchain 1.4.7, langchain-core 1.7.0, langgraph 1.2.16, langchain-openai 1.7.2, openai 3.37.0, drain3 0.9.11. Full pin list in `requirements.lock` (`pip freeze`).
- **Failed attempt:** pyarrow 26.0.0 requires NumPy >= 2, but RCAEval pins `numpy<2` on Python < 3.13. Installed pyarrow 19.0.1 instead (supports NumPy 1.26).
- The installs were slow (about 1.5 hours) because the server home is on NFS; recorded so reruns budget for it.
- All nine Zenodo zips verified against Zenodo's md5 checksums (`~/deeprca-data/raw/fetch.log` on the server).

### Data layout findings (Phase 0; numbers in the audit CSVs)

- Case folders are `<service>_<fault>/<repetition>/`. **Irregularities:** `RE2-OB/checkoutservice_cpu/` also holds a `multi-source-data/` folder and a zip (a demo copy, not a case; RCAEval's `main.py` skips it because it has no `simple_metrics.csv`); `RE3-TT` has a folder `ts-route-service_f3_1/` holding 3 more cases (same service and fault label, different injection times). RCAEval's `main.py` splits folder names into exactly two parts and would fail on it. Our parser (`rca/adapter/layout.py`) accepts an optional numeric variant; ground truth is service `ts-route-service`, fault `f3`. Only numbered repetition folders are cases; anything else is listed in `results/audit_stray_files.csv`.
- RE1 has one wide metrics file (`data.csv`; RE1-SS/TT also `simple_data.csv`); RE2/RE3 have `metrics.csv` (raw container, istio and node metrics, 1 s), `simple_metrics.csv` (RCAEval's derived service-level metrics: cpu, mem, diskio, socket, workload, error, latency-50/90), `logs.csv`, `traces.csv` (OB and TT only), `pod-node-*.csv` (RE2) or pod/node columns in logs (RE3).
- **Traces carry a `parentSpanID` field** in every trace-bearing dataset, so no parent reconstruction is needed (SPEC Phase 1 task 2 not required).
- **Sock Shop has no traces in RE2 or RE3** (README says "N/A"; confirmed). SPEC 2.1 says RE2/RE3 have traces. Consequences: (1) RE2-SS and RE3-SS use the no-trace path (SPEC 7.1, metric-driven investigation with logs); (2) no static call graph can be derived for Sock Shop from traces, so `data/topology/SS.json` is empty, the `topology` tool reports callers/callees as unknown, and `submit_report` check 5 (evidence path) cannot be applied to Sock Shop cases and is skipped there; (3) the code-only ceiling covers only trace-bearing cases.
- Some services report no spans of their own (in Online Boutique, callers' client spans name them, e.g. a `.../CartService/GetCart` client span with no child). The trace tools infer the callee by matching operation tokens to the case's own entity names (normalised: lowercase, alphanumerics only, a prefix shared by all entity names stripped, trailing word "service" stripped), so slow calls to untraced services are attributed. No names are hard-coded.
- Trace service names differ from metric entity names in one dataset (`frontendservice` in traces, `frontend` in metrics, RE2-OB). The adapter maps trace and log service names to metric entities by exact match, then by the same normalisation (`span_service_map` in `results/adapter_report.csv`).
- Status codes are mostly 0/empty in RE2 traces, so error-status evidence is weak in this benchmark.
- Pre-fault data length differs per dataset (median: RE1-OB 6 min with one case at 35, RE1-SS 6, RE1-TT 8, RE2 12, RE3-OB/SS 12, RE3-TT 15; `results/audit_cases.csv`). Correction: an earlier note said RE1-OB had 35 min; that was one case only.
- RE3-SS: 13 of 30 cases contain a `traces.csv` with a header and no rows (the adapter records `has_traces = false`). Some RE3-SS cases contain `root_cause.txt` (the root-cause log line): truth-bearing, never read by the adapter.
- Host entities with IP-shaped names (node exporters, e.g. `192-168-15-8-9100`) appear among RE1-SS/TT metric entities with no pod-to-node file. They are classified as nodes by `node_entity_regex` (system.yaml) when the tool reader loads metrics, so they are not candidate services. The control must be rerun after this change.
- `reports/DATA_AUDIT.md` written from `results/audit_*.csv`. Windows follow RCAEval's baselines: up to 600 one-second rows before and after `inject_time` (`window` in `config/system.yaml`).

### Scorer check (Phase 0 task 3)

- `analysis/scorer_check.py` ran RCAEval's own `main.py` with `dummy` (random ranking) and `baro` on RE2-OB, then re-scored the same result files with `rca/scoring.py`. All 12 per-fault Avg@5 values match `main.py`'s printed values (`results/scorer_check.csv`, column `match`).

### Splits (SPEC 3.2)

- `data/splits.csv` created by `python -m rca.adapter.splits` (seed 20261024) from the raw folder layout, before any case output was inspected. Dev: 42 RE2-OB cases (7 per fault type) and 17 RE3-OB cases (fault types f1 to f5, up to 4 each as available); 59 dev cases. Test: the other 676. md5 `1bc19d3dda1069585d9a2a74bf5a70ef`. Never to change.
- Before the split existed, `tests/test_tools.py` ran on the first converted case of several datasets (pass/fail assertions only; no outputs inspected). After the split, only dev cases are inspected.

### Adapter (Phase 1)

- All 735 cases convert (`results/adapter_report.csv`, column `ok`). Opaque case IDs (`c` + 10 hex of sha1 of dataset/folder/repetition), so no ID reveals service, fault or system. The raw folder name is kept only in `truth.json`.
- Metrics: both the derived service-level file and the raw file are kept (derived names are RCAEval's indicator vocabulary). Counters (`-total`) become per-second rates; `spec-cpu-quota`, `spec-memory-limit-bytes` and `latency-50` are dropped (configuration constants; RCAEval also drops lat-50).
- Logs: Drain3 (sim 0.4, depth 4) per service; messages are masked (UUIDs, hex ids, timestamps, numbers) and deduplicated, baseline-window messages are mined first, and templates first created after the baseline end are marked `in_baseline = false` (`templates.parquet`).
- `tests/test_adapter.py` (span and log row counts equal the raw rows with valid timestamps; every raw metric column except the configured drops is a canonical channel; all 735 converted): passed. `tests/test_truth_isolation.py` (no module under rca/tools, rca/agent, rca/control, rca/guardrails imports rca.truth or rca.scoring; importing them does not load either; the tool reader refuses truth.json; case IDs are opaque): passed.
- **Failed attempt:** the first audit run (system Python, while 10 conversion workers ran) died silently during RE2-TT, most likely killed for memory. Rerun after conversion.

### deepagents API (confirmed against the installed 0.7.26 source)

- `create_deep_agent(model, tools, *, system_prompt, middleware, subagents, backend, response_format, name, ...)` returns a compiled LangGraph graph.
- Built-in tools: `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`, and `task` when sub-agents exist. **No to-do tool is included by default in 0.7.26**, so `langchain.agents.middleware.TodoListMiddleware` is added to the main agent (`write_todos`).
- Sub-agents: `SubAgent` dicts (name, description, system_prompt, tools, model, middleware, response_format) or `CompiledSubAgent` dicts (name, description, runnable). A sub-agent receives only the task description as its message (parent messages and todos excluded) and gets no `task` tool, so it cannot launch sub-agents. The `task` tool returns the sub-agent's structured response (JSON) or its last message.
- Parallelism: several `task` calls in one model step run through LangGraph's tool node; with `ainvoke` they run concurrently. The parallel cap and launch limit are enforced by our wrapper (an asyncio semaphore and a counter around each sub-agent runnable).
- Filesystem: `FilesystemBackend(root_dir, virtual_mode=True)` rooted at `runs/<run_id>/<case_id>/files/`, so evidence persists on disk. A `HarnessProfile` registered for the OpenAI provider excludes `write_file`, `edit_file`, `delete`, `execute`, `glob`, `grep` and disables the auto-added general-purpose sub-agent: agents can only list and read files; evidence is written by code.
- OpenAI: `deepagents` uses the Responses API for `openai:` strings, so we pass `ChatOpenAI(model="gpt-4o-mini", temperature=0, seed=7, use_responses_api=False)` (Chat Completions supports `seed` and returns `system_fingerprint`). The project cannot request `gpt-4o-mini-2024-07-18` by name; the transcript logger checks every response reports that snapshot and stops the run otherwise.

### Phase 3/4 development notes (dev split only)

- **Failed attempt (trace flagging v1):** per-span robust z (median/MAD) flagged single slow outliers. On a dev delay case, cartservice calls with a heavy-tailed baseline (baseline max 1,010 ms) scored z > 700 and filled the top selected traces, while the real fault was a shift of a whole operation (median 3.8 ms to 204 ms). **v2:** a span is flagged only if its own value exceeds its operation's baseline p99 AND the operation is persistently shifted in the window (window p75 vs baseline p75 in units of the baseline p50->p99 spread, `key_shift`); errors only when the operation's error rate rises. Trace selection ranks traces by latency explained by flagged spans and prefers traces covering new flagged operations.
- **Edge gaps blame both ends.** A network fault on one pod slows calls into it and out of it, so the gap on its outgoing call lands on the callee's span. Flagged edges list caller and callee, and tools report a code-computed `slow_calls_by_service` table (slow calls in / out per service).
- **Failed attempts (smoke runs 1-2 on one dev case):** a cache race (parallel tool calls wrote the same temporary file) crashed a sub-agent; tool exceptions aborted sub-agents; a second investigation overwrote a correct finding; the critic answered in prose and never recorded a verdict, so every submit failed and the report was forced; latency metrics with tiny baseline variance (z about 9,000) misled an investigator into blaming a callee. Fixes: process-safe cache; tool errors returned to the model as text; findings write-once with the service set by code; sub-agents end with a schema-validated structured answer that code writes to the evidence file; `metric_anomalies` separates resource metrics from latency/error/traffic metrics and displays z above 100 as 100; a span-investigator launch without a real work item id is refused without running. Smoke run 3 on the same case: accepted report, correct top-1.
- Added check (extension of SPEC 7.6, enforcing SPEC 7.9 in code): `submit_report` rejects a fault type that is not among the `fault_indicators` candidates of the top-1 service (when there are candidates).
- Ranked indicators are normalised in code to `service_indicator` in RCAEval's vocabulary: the agent's valid entries first, then the top service's fault-type indicator, then each ranked service's strongest anomalous metric types.


### Phase 2 and 3 results

- Control run on all 735 cases: `results/control.csv`, `results/control_summary.csv`. Rerun after IP-shaped host entities became nodes (RE1-SS AC@1 changed; the other datasets did not). The control is strong on the dev datasets (dev RE2-OB AC@1 0.857, dev RE3-OB 0.824, `results/control_summary.csv`): beating it on aligned cases is not realistic, which is why the gate (V4) exists.
- **Phase 3 gate passed.** Dev code-only ceiling (true cause among services blamed by flagged spans of the selected traces): first measurement 0.864 (RE2-OB 0.976, RE3-OB 0.588); after the callee-matching fixes below, 0.949 (RE2-OB 0.976, RE3-OB 0.882) (`results/code_ceiling_dev.csv`, rows SUMMARY). Both are above the SPEC's 70% stop line.
- Ceiling misses looked at (dev only): adservice's normalised stem is "ad" (2 letters) and the callee matcher required 3, so slow/failed calls to it were blamed on its caller. Fixed (minimum 2 letters; a trailing plural "s" is also stripped, e.g. "ads"). Socket faults and some code faults leave no trace signature at all; for those the investigators rely on metrics and logs.

### Phase 4: dev iterations (all on the dev split)

Scores per iteration are in `results/eval_dev_v*_summary.csv`.

- **dev_v1 (aborted):** the OpenAI async HTTP client is cached per process and bound to the event loop that created it, so a worker's second case crashed with "Event loop is closed". Fix: one fresh process per case (`max_tasks_per_child=1`).
- **dev_v2:** V3 AC@1 0.424 against the control's 0.847 on the same cases, but AC@3 = 1.0: the right service was always in the top 3 and the agent picked a caller of it. 48 of 59 reports were forced. Three causes found by reading provenance: (1) a prompt rule I had written ("slow calls both in and out of a service point at it") is wrong, because a caller of a slow service also has slow calls in and out; the critic used it to push answers to the caller; (2) the critic sometimes looped (88 model calls, 1.4M tokens) and two cases hit the token limit; (3) the main agent often failed to answer the critic's issues or to give a connected evidence path. **Fixes:** the rule is gone; the slow-call table counts only slow calls into a service; prompts state the correct principle (a caller is slow whenever its callee is slow; blame a caller only with its own evidence that the callee lacks); `evidence_summary` gives code-computed `candidate_facts` (own resource anomaly, own latency anomaly, slow calls into it, verified evidence types, callees that are also candidates); the critic's alternative is annotated by code with its verified positive evidence; per-sub-agent tool-call and model-call limits; rejection messages quote the critic's issues, list services that do have verified evidence, and give a connected path from the new `path_to_symptom` tool; `submit_report` submits the saved draft (the model had been dropping its critic responses between the draft and the submit call); `anomalous_services` refuses to run on traced cases.
- **dev_v3:** RE2-OB V3 AC@1 0.738 (control 0.857); on the 6 symptom-misleading RE2-OB dev cases the agent was right in 5 and the control in 0. RE3-OB (code faults) 0.176: the same caller-blame pattern (frontend for adservice, checkoutservice for emailservice). 30 of 59 still forced; one crash (graph recursion limit).
- Code-fault evidence (dev RE3-OB): the failing service's own logs collapse (e.g. 49 lines against 1,805 expected) with new start-up templates (a restart), and callers log new errors that sometimes name it ("failed to retrieve ads"). Added to `candidate_facts`: the candidate's own log change and new error-like logs in other services that name it (`log_mentions`, same name matching as the callee inference).
- **Interpretation of SPEC 3.4 rule 2 (recorded as a decision):** error status on calls *into* a service (seen by its callers, or on its own server span when called) is counted as positive evidence of type "status", read as part of the SPEC's "caller-vs-callee" evidence: the caller observes a failure the callee causes. The other three types are unchanged.
- `write_draft` now runs the `submit_report` checks as a dry run and lists the failures.
- **dev_v4:** RE2-OB V3 AC@1 0.643, RE3-OB 0.294, no forced reports, but 22 cases ended with no report: the dry run made the main agent redraft until it hit its 60-model-call limit without ever submitting. Fix: bounded drafting (`max_drafts: 5`; the fifth failing draft is recorded as a forced report with its failures). Six RE3-OB cases crashed with HTTP 429 `insufficient_quota`.

### Blocker: OpenAI credits exhausted

- The API key's account ran out of credit during dev_v4 ("You have no credits remaining"). Recorded spend across all runs so far: $5.62 over 182 case runs (sum of `cost_usd` in `runs/*/results.jsonl`). The account apparently held only a few dollars, while the approved Part 1 budget is $500. **All LLM work is paused until the user adds credit.** Non-LLM work continues.


### Model decision (user asked for a final decision; budget is no longer the constraint)

- The user will fund LLM calls with Google Cloud trial credits ($300 per account, several teammates' accounts) and wants the best reachable results. OpenAI access ended (no credit; the project only ever had gpt-4o-mini).
- **Decision: primary model Gemini 3.1 Pro on Vertex AI; Gemini 3.5 Flash as the smaller model for the Part 2 backbone ablation; Gemini 3.7 Flash as the fallback** if 3.1 Pro fails the feasibility checks (tool calling, structured output, quota, repeatability at temperature 0). **Deviation from SPEC 3.5** (GPT-4o / gpt-4o-mini), logged here.
- Why: Google's documentation calls 3.1 Pro its most advanced reasoning Gemini model, and it is an established model with its own documentation and pricing page. Gemini 4 Argon was not chosen: it shows no dated version and no published per-token price, so it risks changing under a frozen run. Claude on Vertex was not chosen: trial credits are not confirmed to pay for partner models. Flash models are faster and cheaper but weaker at multi-step reasoning, which is the system's main weakness on dev (caller-blame).
- Reproducibility: temperature 0, seed 7, fixed thinking level, and the model version reported by Vertex is recorded and checked on every response. Each test run is billed to one account, recorded in the run manifest; the account does not affect results.
- Consequence: the dev tuning done on gpt-4o-mini (dev_v1 to dev_v4) is history. The system is re-tuned on dev with Gemini 3.1 Pro before the freeze. The tools, guardrails and prompts carry over unchanged; prompts may need dev-only adjustment.
- Next: service-account credentials, then the LangChain Vertex integration (API to be checked against the installed package), feasibility checks, dev run, cost projection.


### Vertex AI access and Gemini feasibility checks

- Credentials: service-account key for project `project1-446502` (role Vertex AI User), stored outside git (`credentials/` locally, git-ignored; `~/.config/deeprca/project1-446502.json` on the server, mode 600). The project to bill is chosen per run by `DEEPRCA_GCP_PROJECT` (default: first of `GCP_PROJECTS` in `.env`) and recorded in each result (`gcp_project`).
- **Available on this project (global endpoint):** `gemini-3.1-pro-preview`, `gemini-3.5-flash`, `gemini-3.7-flash`, `gemini-3.5-flash-lite`, `gemini-4-argon`. `gemini-3.1-pro` (without "-preview") returns 404: **Gemini 3.1 Pro is served only as a preview id.** The version check on every response (`expected_snapshot`) stops a run if the served model changes.
- API confirmed against langchain-google-genai 4.4.2 / google-genai 2.33.0: `ChatGoogleGenerativeAI(model, vertexai=True, project, location, credentials, seed, temperature, thinking_config={"thinking_level": ...}, max_output_tokens)`. Usage metadata reports cached input (`cache_read`) and reasoning tokens inside output tokens.
- **Finding (probe in the console, not a results CSV): temperature 0 breaks Gemini 3 tool calls.** Gemini 3.1 Pro, one prompt needing two tool calls, 8 tries each: temperature 0 with high thinking gave 7/8 `MALFORMED_FUNCTION_CALL`; temperature 0 with low thinking 1/8; temperature 1.0 with low thinking 1/8. Google's Gemini 3 guide says to keep the temperature at its default 1.0 and that low values can cause looping or degraded performance. **Deviation from SPEC 3.5 (temperature 0):** Gemini models run at their default temperature, with a fixed seed (7), a fixed thinking level and schema-validated structured outputs. Run-to-run stability is measured and reported as the SPEC requires.
- A middleware (`rca/agent/llm.py`, `MalformedCallRetry`) re-asks the model up to 3 times when a response is a malformed function call (a provider failure, not an answer); retries are counted per case (`malformed_retries`). With retries, at default temperature, 6 tries per setting: 3.1 Pro low thinking 6/6 correct tool calls; 3.1 Pro default thinking 5/6 (one malformed); 4 Argon 12/12; 3.7 Flash 12/12; 3.5 Flash 12/12. Median latency per call: 3.1 Pro 5.5 s, 4 Argon 22 s, 3.7 Flash 7.5 s, 3.5 Flash 3 s.
- **Quota:** 8 concurrent Gemini 3.1 Pro requests on one trial project gave `RESOURCE_EXHAUSTED` errors; runs use fewer parallel cases and client retries with backoff, and test runs can be spread over several projects.
- Prices used for cost accounting (Vertex list price, global, prompts up to 200k tokens): Gemini 3.1 Pro preview $2.00 input, $0.20 cached input, $12.00 output (output includes thinking) per 1M tokens. No per-token price found for Gemini 4 Argon (cost recorded as NaN, tokens kept).
- First full-system case on Gemini 3.1 Pro (dev case, run `gsmoke1`): correct top-1, report accepted at the first submit, no malformed calls, $0.156 and 90 s.
- **Dev model pilot started:** all 59 dev cases on 3.1 Pro with low thinking, then high thinking, then 4 Argon (`scripts/dev_pilot.sh`, runs `pilot_*`). The final choice of model and thinking level is made from dev AC@1, completion and stability, then frozen.


### Gemini 3.1 Pro capacity failure; pilot round 2

- Pilot `pilot_primary` (3.1 Pro, low thinking, 59 dev cases): only 18 cases finished cleanly. 38 crashed with `429 RESOURCE_EXHAUSTED` and 3 hit the wall-clock limit while throttled. Afterwards even a single request is refused, while Gemini 3.5 Flash, 3.7 Flash and 4 Argon answer normally on the same project. Gemini 3.1 Pro preview is served only through the `global` endpoint (every regional endpoint returns 404), so the refusals come from Google's shared capacity for the preview model, not from our request rate. Running the roughly 50,000 model calls Part 1 needs is not feasible on it. **3.1 Pro fails the capacity part of the feasibility check.**
- Partial quality signal before the cut-off (interim, not a results CSV): on the first 25 finished cases, 22 had the correct top-1, the same as the control on those cases. Cost $0.39 per case at list price; only 32% of input tokens were billed at the cached rate.
- Burst test (6 concurrent requests, about 4k-token prompt): 4 Argon 6/6 OK (4-20 s), 3.7 Flash 6/6 OK (about 3 s), 3.5 Flash 6/6 OK, 3.1 Pro 6/6 refused.
- **Pilot round 2:** Gemini 4 Argon vs Gemini 3.7 Flash (the pre-declared fallback) on all 59 dev cases, in parallel (`scripts/dev_pilot2.sh`, runs `pilot_argon`, `pilot_fallback`). Argon's per-token price is unpublished; tokens are recorded and the cost will be taken from billing. Its version label is vague ("3.0"); the per-response version check stops any run if the served model changes.
- Infrastructure fixes: provider throttling (`RESOURCE_EXHAUSTED`) is no longer recorded as a case result. The case is left unrecorded and redone in up to 3 automatic re-passes. Billing exhaustion stops the whole run cleanly; rerunning the same command with another project resumes. `parallel_subagents` lowered 8 to 4; `wall_clock_seconds` raised 1200 to 3600, since throttling inflates time. The 41 throttled cases of `pilot_primary` were removed from it (not results).
- The user checked the Cloud console and saw no credit used yet. Our logs record 861 successful Gemini 3.1 Pro calls billed to `project1-446502` (about 5.9M input, 0.2M output tokens; about $11 at list price). Billing reports lag, usually by hours.


## 2026-10-25

### Pilot round 2 stopped: billing disabled on project1-446502

- Both pilot runs stopped cleanly through the billing stop: every Vertex call on `project1-446502` now returns `403 PERMISSION_DENIED: This API method requires billing to be enabled`, for every model. Finished before the stop (`results/eval_pilot_argon_summary.csv`, `results/eval_pilot_fallback_summary.csv`): Gemini 4 Argon 8 cases, all with correct top-1 and accepted reports (control 7/8 on those cases); Gemini 3.7 Flash 7 cases, all correct and accepted (control 5/7). These samples are too small to choose between the models.
- Mean latency per case was very high: Argon 867 s, 3.7 Flash 1,079 s, with about 10 sub-agent launches per case. 3.7 Flash cost $0.475 per case at list price.
- Tokens logged on this project across all Vertex runs (kept case folders only): 3.1 Pro 3.96M input / 0.13M output; Argon 3.58M / 0.09M; 3.7 Flash 3.53M / 0.18M; smoke test 0.12M input. At list prices this is roughly $20-25, far below the $300 trial credit, so the shutdown is not credit exhaustion. Likely a trial-account restriction (an inactive or unlinked billing account, or a trial that needs a full-account upgrade). The user has to check the Billing page; the cause cannot be seen from the service account.


### Final model decision: Gemini 3.7 Flash (from the dev pilot)

- Resumed on project `mtp1-512709` (new account; service-account key, role Vertex AI User). Probe of the project (real calls): working are gemini-4-argon, 3.8/3.7/3.6/3.5 Flash, 3.5 Flash-Lite, 3.1 Pro preview, 3.1 Flash-Lite, 3 Flash preview, and gpt-oss-120b (Vertex open-model endpoint). Claude models (Opus 4.5-4.7, Sonnet 4.5-4.6, Haiku 4.5) exist but have zero request quota (429). Gemini 2.5 models return 404 (retired); Llama, Qwen and DeepSeek are not available.
- Pilot outcome on the 59 dev cases (interim counts from the run files; `results/eval_pilot_*` once synced):
  - **Gemini 3.7 Flash (`pilot_fallback`):** finished 58 of 59. Top-1 correct in all 58 (RE2-OB 42/42, RE3-OB 16/16); the control was right in 49 of those 58. Every report accepted at submit. $0.37 per case at list price, about 17 min per case. The 59th case crashed in our own code: an evidence entry arrived as plain text instead of a typed item. Fixed (evidence readers accept plain text, typeless entries carry no positive type); the case is being rerun.
  - **Gemini 3.1 Pro (`pilot_primary`):** 34 finished, 32 correct (control 30); 25 cases still throttled after 4 passes.
  - **Gemini 4 Argon (`pilot_argon`):** 30 finished, 30 correct (control 26); 29 still throttled after 4 passes.
- **Decision: Gemini 3.7 Flash is the primary model** (medium thinking, default temperature, seed 7). It is the only one of the three that can run the full workload on trial-account quota, and on dev it was at least as accurate as the two larger models on the cases they finished. **Gemini 3.5 Flash-Lite** is the smaller model for the Part 2 backbone ablation. Both are deviations from SPEC 3.5 (GPT-4o / gpt-4o-mini), logged here.
- Caveat to report: on dev the system was correct on every case it finished, so the dev split no longer discriminates between settings. Tuning the gate and the confidence model on dev is therefore weakly identified (almost no wrong dev answers to learn from). This will be stated in the Part 1 report.


### Flash pilot complete; leakage audit; read-only filesystem fix

- `pilot_fallback` (Gemini 3.7 Flash) after rerunning the one crashed case: 59/59 completed, 59/59 reports accepted at the first submit, V3 AC@1 = AC@3 = AC@5 = 1.0 on dev (RE2-OB 42, RE3-OB 17); control AC@1 0.847 on the same cases; $0.371 per case, 965 s mean latency (`results/eval_pilot_fallback_summary.csv`).
- **Leakage audit (because of the perfect dev score):** every filesystem call in the 59 transcripts was checked. Agents only saw their own case's virtual folder (`/evidence`, `/report`). No tool output contained truth files, raw or canonical data paths, or answer-bearing folder names. The one `execute` attempt was refused (no sandbox). Ground truth was not reachable; the dev score is not a leak.
- **Integrity defect found by the audit:** the read-only file-tool profile was registered only for the "openai" provider, so the Gemini agents (provider `google_genai`) still had `write_file`, `edit_file`, `glob` and `grep`. In a few dev cases sub-agents rewrote hypothesis files directly, bypassing the code-only writers (no effect on ground-truth access). Fixed with two layers: the profile is registered for every provider, and every agent is built with a deny-all-writes filesystem permission. `tests/test_agent_isolation.py` checks both for the primary, small and gpt-4o-mini configurations (4 passed).
- Because the frozen system differs from the pilot system by this fix, a full dev run on the final system (`dev_final`) and the variant smoke tests (`scripts/smoke_variants.sh final`) are running. The gate and the confidence model are fitted on `dev_final`.


## 2026-10-26

### Phase 4 gate passed; freeze

- **`dev_final`** (exact system to be frozen, Gemini 3.7 Flash, 59 dev cases; `results/eval_dev_final_summary.csv`): 59/59 completed, no crashes or limit hits, 59/59 reports accepted (2 after one rejection), V3 and V4 AC@1 = 1.0 (RE2-OB 42/42, RE3-OB 17/17); control AC@1 0.847 on the same cases; $0.294 per case, 515 s mean latency, 8.0 sub-agent launches per case. **Phase 4 gate (at least 95% complete, every report passes submit_report, transcripts and provenance logged): passed.**
- **Variant smoke tests** (`scripts/smoke_variants.sh final`, 3 dev cases each, runs `smoke_final_*`, manifests in `manifests/`): all 11 switches ran to completion with accepted reports: single_agent, code_loop, guardrail off, critic off, model, three injection types, anonymize on, fault_time detect, traces off.
- **Observation (dev, not a tuning target):** on the dev delay case `c038a3fc481` (true cause recommendationservice), most variant runs and one smoke run of the unchanged system ranked productcatalogservice first, while `dev_final` was right. Run-to-run variation on hard cases exists even at a fixed seed. The 3 test runs per case measure it.
- **Gate tuning** (`analysis/tune_gate.py --runs dev_final`, `results/gate_tuning_dev.csv`): every grid point gives the same dev accuracy (V3 is already correct on all 59 cases), so the dev split carries no signal for the gate. Under the SPEC 7.8 objective with ties broken toward the stricter gate, the gate never holds. **Decision: gate thresholds stay null (gate disabled), so V4 equals V3 by construction for Part 1.** The control statistics are still recorded per case for the Part 2 gate analysis (E2). To be stated in the Part 1 report.
- **Confidence model** (`analysis/fit_confidence.py`): cannot be fitted because there are no wrong dev answers (`results/confidence_fit_dev.csv`). The fixed prior weights in `rca/guardrails/confidence.py` are used, and their calibration is reported on the test runs. To be stated in the Part 1 report.
- Full test suite: 40 passed.
- **Freeze:** the configuration, prompts (`*_v1.md`) and code are frozen at the commit tagged `part1-frozen` (hash recorded in the next entry). Test runs wait for the user's go-ahead and teammates' Google Cloud keys (user instruction, 2026-10-26).

- **Freeze commit:** `a6e18f8ccd8da9a0b3072b44a500d7935174f3d5` (tag `part1-frozen`).


### Test runs organised in waves (user request)

- The user asked that the test runs be done in groups, so that partial results are presentable. `analysis/make_test_waves.py` (seed 20261026) split the 676 test cases into **4 waves of 168-170 cases**: stratified by dataset x fault type, shuffled within each stratum and dealt round-robin, so every wave is a representative quarter of the test set (`data/test_waves.csv`, md5 `36405674967cb3be36a12a74c3bb0695`; per-wave case lists `data/test_wave{1..4}.csv`; counts in `results/test_waves_summary.csv`). The dev/test split is unchanged, and the frozen code is unchanged (`rca.run --cases <csv>`).
- **Order (deviation from SPEC Phase 5 step 3, which orders RE2, RE3, RE1 by dataset; requested by the user):** wave by wave for run 1 (results after each wave cover all 9 datasets), then runs 2 and 3 for every wave, then the onset run on the RE2 test cases. Each wave's results are scored after it finishes, with bootstrap confidence intervals, and labelled as partial.
- Funding projects for the test runs: `mtp1-512709` (user) and `project-53e716a1-3b76-4d08-9bf` (teammate). The teammate's project grants the same service account the roles Vertex AI User and Service Usage Consumer, so no key file is needed. Each run records its project.


### Defect found in the first test wave; fixed with the user's approval; re-freeze as part1-frozen-v2

- Wave 1, run 1 (`test_r1`) started from a worktree at `part1-frozen` (commit a6e18f8) on both projects. The first 5 finished cases (all RE1-OB) crashed within seconds: the agent called `select_traces` or `trace_tree` on a case without traces, `CaseData.spans` is None there, and the resulting `TypeError` ended the whole case. `handle_tool_error=True` covers only `ToolException`, so other exceptions escaped. Dev never exercised this: every dev case has traces, and in the traces-off smoke test the agent happened not to call the trace tools. Left alone it would crash a large share of the 450+ no-trace test cases (RE1 and Sock Shop).
- Runs stopped at once (5 finished cases, all crashes; about 3 in flight). Since the user had asked for a frozen system during the tests, they were asked first and approved the fix (2026-10-26).
- **Fix (crash prevention only; no change to how evidence is computed or judged, nothing tuned on test results):** `select_traces` and `trace_tree` return "this case has no traces; use anomalous_services instead" on cases without traces; every tool now catches any exception and returns it to the model as text, counted per case (`tool_errors` in result.json). `tests/test_no_trace_tools.py` calls every agent tool on RE1-OB, RE1-SS, RE2-SS and a traces-hidden RE2-OB case (code tools only, no LLM, no scoring) and checks a raising tool becomes a message. Full suite: 45 passed. Live check with the AI on 2 dev cases with traces off: `smoke_v2_notraces`.
- The aborted run's folder is kept as `runs/test_r1_aborted_v1` (excluded from all results). Wave 1 restarts from scratch on the new freeze.
- Second harness fix in the same version: a case folder without result.json (process killed mid-case) is now wiped before the case is redone, so a resumed run never starts on leftover evidence files. Found when the first traces-off check was killed by an outer 40-minute `timeout` (my mistake; Gemini calls were taking 43-75 s on average at the time).
- **Third defect, found by the traces-off check on 2 dev cases (`smoke_v2_notraces`):** in the no-trace path every anomalous service was registered at its own depth (i+1), so `next_frontier` returned one service per round and the 12 investigators ran one after another instead of in parallel. With Gemini calls averaging about 42 s that day (max about 700 s), both cases hit the 3,600 s wall-clock limit with no report (0 tool errors: the crash fix works). Fix: all service work items at depth 1 (launched in parallel, up to 4 at a time) with an `order` field keeping the deepest-callee-first listing (SPEC 7.1). This changes no evidence and no judgement. Test added (`test_service_items_are_one_parallel_level`).
- Recheck after the parallel fix (`smoke_v2_notraces`): all 12 service investigators launched together (fix confirmed), 0 tool errors. Case `c50e54490db` was correct and accepted in 1,727 s; case `c0849215fce` hit the wall clock (3,600 s). The time went to provider latency, not to the system: main-agent calls averaged 110 s with one call of 1,428 s, consistent with the client's retry-with-backoff under project throttling. Two hypothesis testers failed to return valid structured output (truncated JSON); the main agent continued without them. **Harness changes:** `wall_clock_seconds` 3600 -> 7200 so throttling delays do not end cases (latency is still recorded and reported), and test runs use 2 parallel cases per project instead of 3. No further dev iteration.
- **Re-freeze:** `part1-frozen-v2` at commit `dd73a1915194147e59fef99298120e0af9d2710e`. All Part 1 test results come from this version; nothing from `part1-frozen` (v1) test attempts is used.


## 2026-10-27

### Wave 1, run 1 complete (part1-frozen-v2)

- `test_r1` on wave 1 (170 test cases; 85 per project), frozen worktree at `part1-frozen-v2` (dd73a19, recorded in `manifests/test_r1.json`). Tables: `results/wave_w1_r1_accuracy.csv`, `results/wave_w1_r1_ops.csv`, `results/wave_w1_r1_cases.csv`.
- Completion: 169/170 ok with accepted reports, 1 wall-clock limit hit (RE1-SS, no report), 0 crashes, 0 forced. $0.350 per case at list price ($59.45 total), 17.3 min mean latency, 14.5 sub-agent launches per case.
- Service-level, run 1: V3 AC@1 0.706 (95% bootstrap CI 0.635-0.771), AC@3 0.818, Avg@5 0.806; control AC@1 0.582 on the same cases. Paired against the control: 36 fixed, 15 broken, exact McNemar p = 0.005. Symptom-aligned (99): 0.848 vs 1.000 (15 broken). Symptom-misleading (71): 0.507 vs 0.000 (36 fixed). V4 = V3 (gate disabled). Fault-type accuracy 0.435. Indicator level (151 cases with an RCAEval indicator): AC@1 0.47.
- **Weak spot:** RE1-TT (Train Ticket, metrics only, about 70 services): AC@1 0.355 and AC@3 0.452 vs control 0.484 and 0.774. The no-trace path is weak on a large system. Recorded as a finding; nothing is changed in the frozen system.
- These are partial results (one run, a quarter of the test set) and are labelled as such.

## 2026-10-27: Results file and RCAEval paper comparison

- Added `reports/results.md` at the user's request, updated after each wave: test bed, our results, comparison with the RCAEval paper, strengths, weaknesses and explanations, and a glossary.
- The RCAEval paper (arXiv:2412.17015v2, LaTeX source) reports baselines only on RE2-TT, per fault type, at the service level. `analysis/paper_reference.py` transcribes that table into `results/rcaeval_paper_re2tt.csv` and scores our V3 and the control on the same fault types and average (`results/paper_compare_w1_r1.csv`).
- This deliberately uses copied numbers, which SPEC Section 14 lists as a pitfall. The user asked for it explicitly. The file labels them as reference-only, and Part 2 re-runs the baselines on the same cases.
- Wave 1 RE2-TT result: V3 AC@1 0.778 (23 cases), against the paper's best, multi-source BARO, at 0.690 (90 cases). The CI is wide, so the lead is not certain.

## 2026-10-27: Wave 1 secondary outputs

- `analysis/wave_extras.py` adds the fault-type confusion matrix, confidence calibration and process statistics: `results/wave_w1_r1_faulttype_confusion.csv`, `_faulttype.csv`, `_confidence.csv` and `_process.csv`.
- Fault type (0.435 overall):
  - The system never predicted "loss". 16 of 29 loss faults were called "delay".
  - Socket faults were called "cpu" in 9 of 10 cases.
  - "cpu" was predicted in 72 of 170 cases and was correct in 0.347 of them.
  - Likely cause: `fault_indicators` ranks suggestions by z-score strength, so resource side effects win, and it suggests loss only from drop or error signals. Frozen system, so this is recorded only, not changed.
- Confidence (prior weights, not fitted):
  - The average level is well matched: mean 0.692 against AC@1 0.706.
  - It discriminates weakly: AUROC 0.628.
- Process: 0 guardrail rejections, 0 forced reports, 0 malformed retries, gate never applied.
- `reports/results.md` and the explainer deck are updated with these results.

## 2026-10-28: Ideas kept for later (not approved, no code changed)

The user asked to keep these for Part 2 or a follow-up. Each would be a new, separately reported version, and Part 1 stays frozen.

- **Production trigger:** a trained detector watches sliding metric windows and reports the onset and the visible symptom, which then starts DeepRCA. The first step is the planned `--fault-time detect` run.
- **Trained models inside the pipeline:** a fault-type classifier, a learned final ranker, a learned gate, a fitted confidence model, a learned anomaly detector, and change-point onset detection. The limit is labelled data: only the 59 dev cases may be used, so cross-system validation or a new split would need the user's approval.
- **Coding-agent techniques:**
  - prediction checks for each hypothesis
  - an "unexplained symptoms" feedback loop
  - sandboxed queries and free-text search over logs and traces
  - fault-class playbooks
  - several independent runs with a vote
  - the agent ranking the full list
- **Claims:** "general" holds as a design property only (no system-specific rules, no training, no stored incidents), not as proven performance. The open conditions are the given fault start, likely LLM familiarity with the demo apps (to test with `--anonymize on`), a fixed fault vocabulary, and only 3 systems tested.

## 2026-10-28: Part 3 idea list (after Parts 1 and 2; not approved)

The user asked to collect all future-work ideas as "Part 3". Each item would be a new, separately reported version. The frozen Part 1 system stays as it is.

- **A. Application:**
  - a trained fault detector on sliding windows that starts DeepRCA
  - a production start message (alert, data range, deploy and config history)
  - "no fault" handling: a code fault-presence check before the agent, a `fault_present` field, and test cases built from normal half-windows to measure the false alarm rate
- **B. Accuracy:**
  - tune or redesign the gate for the lost aligned cases
  - let the agent rank the whole list (to fix the weak AC@3)
  - a better no-trace path (rank all services; the 12-service cap)
  - robust metric z-scores, persistence rules and a multiple-testing correction
  - fault-class playbooks
  - fix the `fault_indicators` bias: cpu wins on raw z, and "loss" is never chosen
- **C. Trained parts:** a fault-type classifier, plus a learned ranker, gate and confidence model, trained across systems.
- **D. Agent techniques:** prediction checks per hypothesis, an "unexplained symptoms" feedback loop, sandboxed queries and free-text search, several runs with a vote, and memory of past incidents.
- **E. Generality:**
  - train on all of RCAEval
  - test on an unseen, self-deployed microservice app with chaos fault injection and anonymised names
  - new fault kinds, multiple simultaneous faults, and causes outside the services
- **F. Cost and speed:** skip the agent when the statistics are clearly confident, route to a cheaper model, reuse cached results.
- **G. Extra Part 2 analyses (taken from the OmniRCA report):** narrative faithfulness, instruction compliance, and a census of tools never called. These cost no new runs.

## 2026-10-28: Wave 2 results (run 1)

- `test_r1` wave 2 (169 cases) finished on `part1-frozen-v2`.
  - 168 accepted reports, 1 with no report (RE1-OB), 0 crashes, 0 limit hits.
  - Cost $57.77; 11.4 min mean per case (`results/wave_w2_r1_ops.csv`).
- Wave 2 accuracy: V3 AC@1 0.751 (CI 0.686–0.817) against the control's 0.609; 42 fixed, 18 broken, McNemar p = 0.003 (`results/wave_w2_r1_accuracy.csv`).
- Waves 1–2 combined (339 cases, `results/wave_w12_r1_*.csv`):
  - AC@1 0.729 (CI 0.681–0.776) against 0.596; 78 fixed, 33 broken, p < 0.001
  - AC@3 0.850 against 0.805
  - misleading cases 0.569 against 0; aligned 0.837 against 1.0 (33 broken)
  - RE1-TT significantly below the control (0.306 against 0.484, p = 0.043)
  - fault type 0.413; "loss" never predicted
  - confidence AUROC 0.634
- RCAEval paper comparison on RE2-TT (46 cases): V3 0.842 / 0.884 / 0.876 (AC@1 / AC@3 / Avg@5) against the paper's best, multi-source BARO, at 0.690 / 0.820 / 0.810 (`results/paper_compare_w12_r1.csv`).
- `analysis/wave_report.py` now computes the exact McNemar p itself (column `mcnemar_p`). Before this, wave 1's p-values were added by hand after the script ran. The wave 1 tables were regenerated with the script, and the values are unchanged.
- `reports/results.md` now reports waves 1–2 combined.

## 2026-10-28: Part 2 started before Part 1 is complete (user decision)

- The user approved starting Part 2 now, before the Part 1 report and review. This is a deliberate exception to the CLAUDE.md rule, made by the user.
- Part 1 stands at waves 1–2 of run 1 (339 test cases). Waves 3–4, runs 2–3, the detect run and the Part 1 report are deferred until credit allows.
- Part 2 uses those 339 cases as its shared case set. Every Part 2 conclusion is labelled "on 339 cases, one run".
- The system stays frozen at `part1-frozen-v2` (dd73a19). Part 2 adds new code (baseline wrappers, analysis scripts) only outside the frozen worktree.
- Part 1 and Part 2 paid runs never run in parallel, because they share the provider quota.
- Credit remaining, as reported by the user: account 1 ₹19,538 of ₹28,797; account 2 ₹24,856 of ₹28,797; about ₹44,400 in total.
- Order:
  1. free work first: RCAEval baselines through the library, and analyses of the stored logs
  2. then a measured cost projection for the paid runs (SPEC Phase 6 step 5 and Section 9.3), for the user's approval

## 2026-10-28: Part 2 Phase 6: RCAEval baselines (free runs)

- **Case set:** the 339 test cases of waves 1–2 (`data/test_waves.csv`, waves 1 and 2). Outputs go to `runs/rcaeval/w12/`.
- **How they run:** `baselines/run_rcaeval.py` runs RCAEval's own `main.py` (commit 2fca61b, unmodified, default `--length 20`). Each method and dataset gets its own working folder, with a symlinked `data/` tree in the layout `main.py` expects.
- **Folder `RE3-TT/ts-route-service_f3_1` is left out of the data RCAEval sees.** `main.py` splits the fault folder name into exactly (service, fault), so this name would stop the run. Its cases count as misses for the `main.py` methods.
- **Methods through `main.py`:**
  - BARO and CIRCA on all 9 datasets
  - multi-source BARO and multi-source CIRCA on the 6 RE2/RE3 datasets (RE1 has no logs or traces)
- **Trace methods through `baselines/run_trace_methods.py`:**
  - In RCAEval 2fca61b, `main.py` passes the metrics table to `tracerca` and `microrank`, which expect the span table. Both fail with `KeyError: methodName`.
  - So both are called through the library functions with `traces.csv` and the injection time in microseconds, as their own code comments show. Their code is unchanged.
  - `pdiagnose` exists only as a demo `main()` with hard-coded paths. Its body is reproduced with the paths as parameters; its logic is unchanged.
  - These run on cases that have traces (RE2-OB, RE2-TT, RE3-OB, RE3-TT, some RE3-SS): 98 cases.
- **Not run:**
  - **MicroCause:** fails inside RCAEval (`TypeError: 'NoneType' object is not subscriptable`, after 985 s on the 2-case smoke test).
  - **CausalRCA:** no case finished within about 40 minutes on the shared server (load about 66 on 48 cores); stopped.
  - Both scored low in the RCAEval paper (RE2-TT AC@1 0.10 and 0.22). They can be retried later if time allows.
  - **RCD and multi-source RCD** need RCAEval's separate Python 3.8 environment. To do.
- **Scoring:** `analysis/baselines_collect.py` maps each output file to our case ID and scores it with the same Evaluator. It compares each method with V3 and the control on the same cases (exact McNemar).

## 2026-10-28: RCLAgent dropped from Phase 6 (user decision)

- The user decided RCLAgent will not be run, which is a deviation from SPEC Phase 6 step 3.
- Hypothesis H6 ("competitive with RCLAgent and RCAEval's best baselines") is therefore tested only against the RCAEval baselines. Any reference to RCLAgent in reports must say it was not re-run.

## 2026-10-28: Part 2 Phase 8, free analyses of the stored runs (waves 1–2, 339 cases, one run)

Scripts are `analysis/p2_*.py`; results are in `results/p2_*.csv`.

- **A1 (who decides):**
  - Origin of the final answer: investigators 37.8%, main agent 31.0%, code tools 17.7%, testers 13.0%, critic 0.6% (`p2_a1_summary.csv`).
  - At its first draft, the main agent **overrode** the code evidence leader (support score) in 184 of 337 cases. That fixed 121 answers and broke 4. Where it overrode, the evidence leader alone was right in only 9.8% of cases.
  - So, unlike OmniRCA (first agent 82%), no single component dominates. The main agent's synthesis adds most of the value over plain evidence counting.
- **A2.4 (does evidence disconfirm):**
  - 164 of 3,306 findings (5.0%) cleared their suspect, and 13.7% carry a substantive counter-observation. 215 of 1,166 hypotheses (18.4%) were refuted. OmniRCA had 0 of 329 disconfirming items.
  - **Defect:** 84.2% of hypothesis files have no evidence-for items, and 98.7% have no evidence-against items. Testers give verdicts without the structured evidence, so their verdicts are weakly grounded (`p2_a24_summary.csv`).
- **B3 (errors, 92 wrong #1 answers):**
  - unrelated 42.4% (37 of 39 on TT), no call graph (SS) 27.2%, sibling 10.9%, downstream 9.8%, upstream caller 5.4%, entry point 4.3%.
  - Unlike OmniRCA (23 of 30 blamed a caller), the "blame the caller" error is rare. Most errors are distant wrong picks on Train Ticket (median 3 hops).
- **B4 (what predicts failure):** success correlates with n_anomalous at r = −0.33 and with n_services at r = −0.33 (OmniRCA: −0.34). App size and crowding are confounded. The top-2 margin predicts the control (r = 0.30) but not V3 (0.01).
- **C5 (code flags vs agent):**
  - Code registered the true cause as a suspect in 75.2% of cases. When it did, the agent was right in 87.8%. The agent was also right in 23 cases code had not flagged.
  - **RE1-TT: code flagged the true cause in only 21.0% of cases.** This confirms the 12-service cap on the no-trace path as the main cause of the RE1-TT weakness. RE3-TT: 33.3%.
- **D2 (calibration):**
  - Underconfident on OB and SS (gap −0.20, −0.13), overconfident on TT (+0.17, RE1-TT +0.34).
  - AUROC 0.634 overall, below 0.5 on RE1-SS (0.427).
- **Tool use and compliance:**
  - Every registered tool was called at least once.
  - Prompt steps were followed in 98.8–99.7% of cases, except one: on cases without traces (258), the agent called `select_traces` first in 88% even though the start message lists no traces. It got the error message and then called `anomalous_services`, so the only cost was a wasted call.

## 2026-10-28: Part 2 Phase 7 launched (Option A); OmniRCA not re-run

- The user asked to complete Part 2. Phase 7 uses **Option A**, a fixed 100-case sample, about $190 projected, within the remaining credit (about ₹44,400).
- **OmniRCA is not re-run.** The comparison is design-level, from the user's OmniRCA analysis report, and is labelled indicative: different cases and model, no per-case data. If `master_cases.csv` becomes available, a per-case match on overlapping cases is free.
- **Samples** (`analysis/p2_sample.py`, seed 20261028, drawn once):
  - `data/p2_sample.csv`: 100 cases, per-dataset quotas proportional to the 339, misleading first up to half (48 misleading, 52 aligned)
  - `data/p2_a2_cases.csv`: 20 sample cases where V3 was right, for planted false leads
  - `data/p2_c3_cases.csv`: 27 sample cases with traces
- **Injection files:**
  - plausible = most anomalous non-true service; implausible = least anomalous service (full control ranking)
  - types: `fake_flagged_span` and `wrong_candidate_rank`
  - The third type, `false_hypothesis`, is skipped to save cost.
- **Experiments** (`scripts/p2_phase7.py`, run ids `p2_*`, frozen worktree dd73a19, 2 cases at a time per project):
  - noCritic, noGuard, single agent (V1), code loop (V2) and the small model (Gemini 3.5 Flash-Lite), each on 100 cases
  - A2: 4 configurations × 20 cases
  - hidden names (anonymize) and traces off, each on 27 cases
  - 638 runs in total
- **Covered without new runs:**
  - **H5 transfer:** the frozen system was tuned only on Online Boutique dev cases (RE2-OB and RE3-OB), so its Sock Shop and Train Ticket test results already are the transfer check.
  - **C3(b), prompt stripped to a bare ID:** the start message already carries only the case ID, data types and window.
- **Not run:** C3(c), name shuffling. There is no switch for it in the frozen code, and adding one would change the system.

## 2026-10-28: C4 faithfulness; trace baselines hung and restarted

- **C4** (`results/p2_c4_summary.csv`): 9,957 of 9,987 checked numeric claims in the findings match the code's recomputation within 5% (99.7%).
  - metric z-values: 9,638 of 9,667
  - own times: 194 of 194
  - edge gaps: 125 of 126
- **Most of the 30 "mismatches" are not agent errors.** They are machine-level (node) metrics quoted by the agent, and the checker recomputes service metrics only. That is a gap in the checker.
- One real mismatch: an edge-gap claim quoting the callee's p90 latency, which is not a span value.
- Unlike OmniRCA (7 of 8 "z-scores" mislabelled), every DeepRCA metric tool reports a true z-score under that name, so the labels cannot drift.
- **Trace baselines hung.** Both `run_trace_methods.py` runs were alive but at 0% CPU: forked workers deadlocked under pandas threads. The workers now start with "spawn", and both runs were restarted. Finished cases are kept.
- Two `ssh … pkill -f run_trace_methods` commands also killed their own session, because the pattern matched their own command line. Use `pgrep -f "[r]un_trace_meth"`, in a command that contains no other mention of the script.

## 2026-10-28: Phase 7 reordered for the OmniRCA comparison; D1 stability re-run added

- The user's priority is Phase 8 and its comparison with OmniRCA. The experiments that match OmniRCA's analyses now run first:
  1. A2 planted false leads
  2. C3.2 hidden names
  3. D1 stability
  4. model comparison
  5. then the ablation ladder: no critic (resumes from its 20 finished cases), no guardrail, single agent, code loop, traces off
- **New: `p2_rerun`.** The frozen system is re-run unchanged on 34 sample cases (`data/p2_d1_cases.csv`, every third sample case), for run-to-run stability. Projected about $12, still within Option A.
- The cases interrupted by the restart are redone from scratch. `rca.run` deletes unfinished case folders.

## 2026-10-28: Faster finish, no further cuts (user decision)

- The user asked for the earliest finish with nothing more dropped or shrunk.
- A **second Phase 7 runner** (`--only p2_single p2_codeloop p2_notraces`, log `~/p2_phase7_b.log`) runs those three experiments now, in parallel with the main runner. That is 8 cases at once instead of 4.
  - The main runner reaches them only after A2, hidden names, the re-run, the small model, no critic and no guardrail, about 20 hours from now. By then they will be marked done, so the main runner skips them.
- **The trace baselines hung a second time.** The spawned workers disappeared (the shared server had 2–4 GB free; another user holds about 106 GB) and the pool waited forever.
  - They now run in-process, one case at a time: TraceRCA and PDiagnose in one process, MicroRank in another.
- **Leftover processes:** killing an `rca.run` parent leaves its spawned case workers running (parent PID 1). They finish their case and write a valid result.
  - Before any restart of a run id, those orphans must be stopped too. Otherwise a redo of the same case could collide with them.

## 2026-10-29: Slow Train Ticket baselines moved to Kaggle (user's account; plan agreed)

- **Why:** on the shared institute server (another user holds about 106 GB of RAM and most CPU), the Train Ticket baselines were projected at days.
  - CIRCA on RE2-TT: 4 of 46 cases in 17 hours, about 200 hours left.
  - CIRCA on RE1-TT: about 38 hours left. CIRCA on RE3-TT: about 29 hours left.
- **Kaggle token:** the user's `kaggle.json` is placed on the server at `~/.kaggle/kaggle.json` (mode 600) and gitignored locally.
- **Server side:** the CIRCA Train Ticket runs were stopped. Their finished cases are kept: RE1-TT 23, RE2-TT 4, RE3-TT 5.
- **Kaggle side:** `baselines/kaggle_jobs.py` built 5 private CPU notebooks (`hemant159/deeprca-bl-0..4`) covering the remaining 148 case-runs: CIRCA on RE1/RE2/RE3-TT and multi-source CIRCA on RE2/RE3-TT. Each notebook:
  - clones RCAEval at 2fca61b and installs it on Python 3.12 through uv
  - downloads the zips from Zenodo record 14590730 and extracts only the files `main.py` reads (`data.csv` or `simple_metrics.csv`, `inject_time.txt`, `logts.csv`, `tracets_*.csv`)
  - runs the unmodified `main.py`, one process per core on case subsets, with one thread per process
  - syncs results to `/kaggle/working` every minute and stops itself at 11 hours
- **Collection:** `kaggle_jobs.py fetch` copies the results into `runs/rcaeval/w12/`.
- **Server now runs:** multi-source BARO on all six RE2/RE3 datasets; multi-source CIRCA on RE2-OB, RE2-SS, RE3-OB and RE3-SS; RCD and then multi-source RCD; MicroRank; and Phase 7.

## 2026-10-29 16:40 IST: Phase 7 status, Kaggle RCD fix

- **Kaggle RCD round failed.** All three `deeprca-rcd` notebooks ended in ERROR. Cause: `tigramite==4.2.2.1` (an `[rcd]` extra) imports numpy in its setup.py, and uv builds it in an isolated env without numpy. The server env had worked because pip 20 builds legacy packages without isolation.
- **Fix** (`baselines/kaggle_jobs.py`): install `numpy==1.23.5` (the server env-rcd version) plus setuptools and wheel first, then the extras with `--no-build-isolation`. Rebuilt the 5 shards (134 case-runs: rcd RE1-TT 45, RE2-TT 30; mmrcd RE2-TT 46, RE3-TT 13) and pushed rcd-0..2. rcd-3/4 wait for a free Kaggle slot (5-session limit).
- **No-critic stopped at 68 of 100** (throttled cases, no result written). The 32 missing cases are queued to run after no-guardrail finishes (`~/p2_phase7_d.log`, marker `~/p2_nocritic.really_done`).
- **Rerun (34/34) and traces-off (27/27) are complete** (`results/p2_variants_summary.csv`):
  - rerun: same #1 as run 1 in 82.4%, 0 fixed / 2 broken
  - traces-off: 0.481 vs 0.778, 4 fixed / 12 broken, p = 0.077

## 2026-10-29 17:45 IST: Kaggle RCD fails again; exact-version install

- **Second failure.** The second RCD round failed on `cairocffi==1.5.1`, which needs cffi at build time.
- **Fix.** Rather than fixing packages one at a time, the notebook now installs the server env-rcd's exact `pip freeze` (`baselines/rcd_requirements.txt`, 177 packages). The steps:
  - numpy 1.23.5 and cffi 1.15.1 go in first
  - the rest is installed with `--no-build-isolation`
  - RCAEval itself is installed `--no-deps`
- **Tested** on the server in `/tmp/rcdtest` with uv and Python 3.8: `from RCAEval.e2e import rcd, mmrcd` works.
- **Multi-source baselines apply to RE2 only.** RCAEval's `main.py` multi-source path reads `logts.csv`, `tracets_err.csv` and `tracets_lat.csv`. These preprocessed files exist in the RE2 cases but not in RE3, which ships only raw `logs.csv` and `traces.csv`.
- mmrcd on RE3-OB and RE3-SS therefore stopped at once with FileNotFoundError. mmbaro and mmcirca have no RE3 results either. Their RE3-TT shards on Kaggle will fail the same way within seconds.
- **Decision:** multi-source BARO, CIRCA and RCD are reported on RE2 only, using RCAEval unmodified. We do not build the missing files ourselves, since that would be our preprocessing, not theirs. `baselines_collect.py` already counts a method only on datasets where it produced output.

## 2026-10-29 19:00 IST: RCLAgent paper comparison (published numbers only)

- **Sources.** RCLAgent v1 (arXiv:2508.20370) reports only AIOps 2022 results, with no RCAEval numbers. The follow-up (arXiv:2605.14866v1, May 2026, Table I) reports on RCAEval, but only on RE2-OB, because RCLAgent needs traces, metrics and logs together. It uses Recall@1/3/5/10 and MRR with Claude-3.5-Sonnet and Qwen-3.6-Plus.
- **Transcription.** The table is transcribed in `analysis/rclagent_reference.py`, which writes `results/rclagent_paper_re2ob.csv` and `results/rclagent_compare_w12_r1.csv`. RCLAgent itself is not re-run (user decision).
- **Our side.** The 24 RE2-OB test cases in waves 1–2, with V3, the control, and our RCAEval runs of BARO, TraceRCA and MicroRank on the same cases.
- **Protocol check.** RCAEval BARO run by us scores R1 12.5%; the paper gives 18.9%. Both are low because RCAEval's BARO ranks the noisy `redis_diskio` metric first in every case we inspected. The paper's baseline numbers therefore match the standard RCAEval setup.
- **Caveats.** Different case sets: ours is 24 test cases, theirs is the paper's RE2-OB set, case count not stated. Different models. Indicative only, no paired test.

## 2026-10-29 19:40 IST: fair RCLAgent comparison without re-running it (user decision)

- **User decision.** RCLAgent stays not re-run, but the comparison must be fair. What can be matched without running it is now matched (`analysis/rclagent_reference.py`):
  - **Same cases.** All 90 RE2-OB cases, the set the RCLAgent-V2 README evaluates ("90 fault injection cases", per-fault). DeepRCA runs on the 66 we had not yet run:
    - 24 test cases of waves 3–4, run id `test_r1`, the normal Part 1 run 1
    - 42 dev cases, run id `p2_re2ob_dev`
    - Both are queued after the no-critic leftovers (`~/run_re2ob_all.sh`), cost about $0.35 per case.
    - The dev cases were used for tuning, so the all-90 row is flagged; the clean test-only row (48 cases) is reported beside it.
  - **Same metrics.** Recall@1/3/5/10 and MRR as defined in the paper.
  - **Same baselines.** BARO, TraceRCA and MicroRank are re-run by us through RCAEval on all 90 cases (tag `re2ob_all`), to check that our setup reproduces the paper's baseline numbers.
  - **Statistics.** Exact 95% CI on R1, and an exact one-sided binomial test against each published RCLAgent R1, treated as a fixed reference.
- **Not removable without running RCLAgent:**
  - The model: theirs is Claude-3.5-Sonnet or Qwen-3.6-Plus, ours is Gemini 3.7 Flash.
  - Their scoring: their `evaluate.py` takes the best rank across all error traces of a case, which is lenient to RCLAgent; we give one answer per case.

## 2026-10-29 20:10 IST: RCLAgent comparison from reported numbers only (user decision)

- **User decision.** Nothing is run for the RCLAgent comparison. Our already-reported results are compared with the paper's RCLAgent (Claude-3.5-Sonnet) row, and the model difference is stated, not used as a reason to withhold the comparison.
- **Cancelled before any case ran:**
  - the queued DeepRCA runs on the other 66 RE2-OB cases (`run_re2ob_all.sh`)
  - the `re2ob_all` baseline runs; their partial outputs were deleted
- **Script.** `rclagent_reference.py` now scores only the 24 RE2-OB test cases of waves 1–2 (test_r1).
- **Checked along the way:** Claude-3.5-Sonnet returns 404 on both Vertex projects (retired); Claude Sonnet 4.5 has zero quota on them. Neither is used.

## 2026-10-29 20:40 IST: fairest RCLAgent comparison from existing results

- **Three views** (`analysis/rclagent_reference.py`; `results/rclagent_compare_w12_r1.csv`, `results/rclagent_lift_w12_r1.csv`):
  - **home:** RE2-OB, DeepRCA's tuning app, an upper bound
  - **unseen:** RE2-SS and RE2-TT, never used in development but with the same data types and fault types, so conservative for DeepRCA
  - **gain over BARO:** each system minus RCAEval's BARO on its own cases
- **Unseen apps, DeepRCA:** R1 85.6% (90 cases, CI 76.6–92.1), MRR 89.3, against RCLAgent-Claude's R1 52.3% and MRR 63.0 on its paper's RE2-OB.
- **Gain over BARO at R1:** RCLAgent +33.4 points; DeepRCA unseen +46.7, home +87.5.
- **Gain over BARO at R3, R5 and R10:** RCLAgent is below BARO (−29.1, −20.6, −14.0); DeepRCA is at or above it.
- **Protocol check:** our RCAEval BARO on RE2-TT scores R1 67.4%, consistent with the RCAEval paper's BARO average (0.67).
- **Not covered:** TraceRCA and MicroRank have no output for RE2-SS (it has no `traces.csv` in our data), so the unseen view uses BARO only.

## 2026-10-29 20:35 IST: Kaggle login mix-up and fix

- **Cause.** Another project on the same server login (`~/ubiqui_comp`, unrelated to DeepRCA) logged the shared `~/.kaggle` into another Kaggle account at 18:57. At 19:19 our `push_rcd34.sh` polled the CIRCA notebook status under that login and got "not found". It treated the error as "finished" (a flaw in the script) and pushed `deeprca-rcd-3` and `deeprca-rcd-4` to the other account.
- **Fix.** `kaggle_jobs.py` now runs every Kaggle command with `KAGGLE_CONFIG_DIR=~/.kaggle_deeprca`. That folder holds only hemant159's `kaggle.json`, and the script refuses to run if it holds anything else. `--only` limits push, status and fetch to named shards. Nothing in `~/.kaggle` was changed.
- **Re-pushed** rcd-3 and rcd-4 to hemant159; both are RUNNING, alongside rcd-1 and bl2-0/1. rcd-0 and rcd-2 are COMPLETE, to be fetched. The copies on the other account were left untouched.

## 2026-10-29 22:30 IST: fair unseen-app comparison and supervisor deck

- **`analysis/p2_unseen_compare.py`** (`results/p2_unseen_baselines.csv`, `results/p2_unseen_systems.csv`):
  - **Scope.** Only Sock Shop and Train Ticket test cases (245), since DeepRCA was tuned on Online Boutique only. Each RCAEval baseline is scored on the unseen cases it has finished. Cases still running on Kaggle are excluded and counted as pending. DeepRCA is scored on exactly the same cases (paired, exact McNemar).
  - **Result.** DeepRCA beats every baseline, with p ≤ 0.002 in every row. The best baseline is PDiagnose at 47.8% vs DeepRCA's 71.6% on the same 67 cases. DeepRCA scores 66.1% on all 245 unseen cases vs the control's 55.5%.
  - **Agent systems:** gain over each system's own statistical baseline, from published numbers:

    | System | Data | AC@1 vs own baseline | Gain |
    |---|---|---|---|
    | DeepRCA | RE2-TT | 84.8 vs 39.1 | +45.7 |
    | OmniRCA | RE2-TT | 42.9 vs 60.7 | −17.9 |
    | RCLAgent | RE2-OB, paper | 52.3 vs its BARO 18.9 | +33.4 |

- **Venue dates** were checked on 29 Oct from the official DSN and KDD calls and se-deadlines.github.io. ISSRE and ASE 2027 dates are not yet announced.
- **Supervisor deck** "DeepRCA: Progress Review" (40 slides) is published as a private artifact.

## 2026-10-30: Kaggle token override fixed; baselines and no-critic complete

- **Second Kaggle account mix-up, root cause.** kaggle 2.2.5 (kagglesdk `get_access_token_from_env`) reads `~/.kaggle/access_token` before any `kaggle.json`, whatever `KAGGLE_CONFIG_DIR` says. The other project on this login wrote another account's token there on 2026-10-29 at 18:57, so the 2026-10-29 wrapper (which checked only the username inside `kaggle.json`) passed while the CLI authenticated as the other account (`kaggle config view` showed `auth_method: ACCESS_TOKEN`).
- **Fix** (`baselines/kaggle_jobs.py`): run the CLI with `HOME=~/.kaggle_deeprca_home` (kept empty) and without `KAGGLE_API_TOKEN`, and refuse to run unless `kaggle config view` reports hemant159 without an access token. The other project's token file was left untouched.
- With the fix, bl2-0, bl2-1 and rcd-0 to rcd-4 all show COMPLETE on hemant159. Fetched: bl2-0 9, bl2-1 8, rcd-1/3/4 24 each.
- Re-ran `baselines_collect.py --tag w12 --ours wave_w12_r1` and `p2_unseen_compare.py` (`results/p2_unseen_baselines.csv`). DeepRCA still beats every baseline on the same unseen cases (all p ≤ 0.002). Still unscored: 11 RE2-TT multi-source BARO cases (status `missing`, no output) and 2 of 245 cases for CIRCA, BARO and RCD.
- No-critic finished 100/100: AC@1 0.68 vs V3 0.69, 7 fixed and 8 broken, p = 1.0 (`results/p2_variants_summary.csv`). No difference, like no-guardrail and the fixed code loop.
- Deck: slides cmp-baselines and an-ablation updated. References section replaced with one page per OmniRCA framework theme (A–D), written from the full report text.
- **Deck (user decision 2026-10-30):** single-agent claims removed from the presentation (an-ablation row and title, fw-groups, fw-next step 4, pub-plan finding and timeline, summary). The p2_single result stays in `results/p2_variants_summary.csv`; it is not deleted or re-run.

## 2026-10-30: Part 2 closed out (Phase 6 gate, FINDINGS, report)

- **Phase 6 gate passed.** `analysis/baselines_gaps.py` writes a reason for every baseline case without a ranking (`results/baselines_gaps.csv`):
  - TraceRCA, PDiagnose, MicroRank: crash inside RCAEval when a fault-window operation never occurs in the normal window (`KeyError` in `tracerca.py:59`, shared by the other two). Checked that `run_trace_methods.py` passes the full `traces.csv` unchanged, so the crash is RCAEval's, not our setup's. MicroRank on RE3-SS: empty array in `microrank.py:34`.
  - Multi-source BARO RE2-TT: RCAEval `main.py` stops the whole run on the first exception. It crashed on `ts-train-service_socket/1` (empty array in `mmnsigma`), so the 10 later cases never ran. Re-ran the crashing case alone (`w12fill_a`, same error, recorded as failed) and the 10 others (`w12fill_b`, all ok); results copied into `w12`. Multi-source BARO now covers 90 of 90 unseen cases.
  - BARO, CIRCA, RCD on RE3-TT: `main.py` cannot parse the folder name `ts-route-service_f3_1`, so its 2 cases are never seen (2 of 245).
- **Unseen comparison, answered-only view added** (`p2_unseen_compare.py`, column `view`): crashes left out instead of counted as misses. DeepRCA leads all nine baselines; PDiagnose's gap is not significant (69.6 vs 78.3 on 46 cases, 8 / 4, p = 0.388). Deck slide cmp-baselines now shows this view; summary and pub-plan say "8 of 9 significantly".
- **C5 extended** with `results/p2_c5_by_fault.csv`: only 81 test cases get suspects from traces (RE1 and the Sock Shop sets have none); trace and metric paths both hold the cause about 78% of the time.
- **Phase 8 deck:** single-agent row and verdict bullet removed (user decision), no-critic and no-guardrail rows updated to 100 cases.
- **`reports/FINDINGS.md` complete** (no pending sections). The single-agent result is kept there as a measured result, noted as removed from the presentation. **`reports/report.html` written** in the OmniRCA report's structure; it leaves the single-agent result out, consistent with the presentation.

## 2026-10-31: single-agent result removed from FINDINGS.md

- User decision: the single-agent variant is removed from `reports/FINDINGS.md` as well (row in C1 and its note), matching the presentation and `report.html`. The run and its numbers remain in `results/p2_variants_summary.csv`.

## 2026-10-31: thesis first draft (MTP-1 report)

- LaTeX draft in `thesis/` (`main.tex`, `chapters/`, `references.bib`), following the IIT KGP M.Tech report guidelines. Builds with `latexmk -pdf main.tex`.
- Sources: SPEC, `reports/FINDINGS.md`, `reports/results.md`, `results/*.csv`, the BTP-2 OmniRCA report and the OmniRCA analysis report ("OmniRCA Under Test"). Appendix D maps every table to its source.
- Pending work is marked in the text and listed in `thesis/TODO_FINALISE.md` (waves 3–4, onset run, paired OmniRCA/RCLAgent re-runs, missing ablation rungs and Holm correction, three-run stability).

## 2026-10-31: thesis gaps closed without new model runs

- **Holm correction** (`analysis/p2_holm.py`, `results/p2_holm.csv`): 13 paired tests behind the claims (V3 vs control on all, misleading, aligned and unseen-application cases; V3 vs nine baselines, answered view). All that were significant stay significant; weakest corrected p = 0.024 (unseen vs control, TraceRCA); PDiagnose stays non-significant.
- **Code-only rung V1** (`analysis/p2_v1_code_only.py`, `results/p2_v1_*.csv`): code-flagged suspects ranked by a fixed rule (traced cases: deepest flagged span first, ties by own/gap z; no-trace cases: code's callee-first order), rest of the list from the control; no LLM. AC@1 0.248 vs V3 0.729 on 339 cases (1 fixed, 164 broken); below the control (0.596) but fixes 26 misleading cases. V2 (agent without sub-agents) is not reported, as the single-agent result was removed by the user.
- Thesis now builds with XeLaTeX (Times New Roman); references checked; OmniRCA/RCLAgent re-run box turned into a limitation (OmniRCA's GPT-4o no longer accessible; RCLAgent not run by user decision).
- Still pending: paid runs (waves 3–4, onset run, repeat runs) awaiting the user's approval; personal and degree details.

## 2026-10-31: remaining Part 1 test runs launched (user approval)

- The user approved the remaining paid runs and asked for them to run in the background, as fast as possible, with nothing skipped: waves 3–4 run 1 (337 cases, run id `test_r1`), the onset-detection run on the RE2 test cases (`test_detect`, `--fault-time detect`), and runs 2–3 on all 676 test cases (`test_r2`, `test_r3`). Estimated at the measured $0.35 per case.
- Launcher `scripts/test_runs.py` (stages in that order, frozen worktree `part1-frozen-v2`, both Google Cloud projects, 3 cases at a time per project, up from 2, for speed; restartable). Log `~/test_runs.log` on the server.
- The thesis keeps placeholder boxes for these results until they finish. Naming note: the code-only ranking added earlier (`p2_v1_code_only.py`) is not the SPEC's V1 rung; the thesis calls it "code only, no model".

## 2026-10-31: test run 1 complete (all 676 test cases)

- `test_r1` waves 3–4 (337 cases) finished on `part1-frozen-v2`: 334 accepted, 1 forced, 2 no report, 0 crashes; $111.90 ($0.33 per case), 8.4 min mean per case (`results/wave_w34_r1_ops.csv`).
- Waves 3–4: V3 AC@1 0.682 (CI 0.632–0.733) against the control's 0.599; 57 fixed, 29 broken, p = 0.003 (`results/wave_w34_r1_accuracy.csv`).
- All 676 test cases (`results/wave_all_r1_*.csv`):
  - AC@1 0.706 (CI 0.672–0.740) against 0.598; 135 fixed, 62 broken, p < 0.001; AC@3 0.830 against 0.794
  - misleading 0.496 (n = 272) against 0; aligned 0.847 (n = 404), 62 broken
  - RE1-TT still significantly below the control (0.296 against 0.464, p = 0.002)
  - fault type 0.411, "loss" never predicted; confidence AUROC 0.662
  - cost $229.12 in total
- Thesis Ch. 8 now reports the full test set (with waves 1–2 and 3–4 rows in the overall table); abstract, setup and conclusions updated. The baseline comparisons, ablations and Ch. 9 framework analysis stay on waves 1–2 (339 cases), labelled as such.
- The launcher moved on to `test_detect` (228 RE2 test cases, `--fault-time detect`).

## 2026-10-31: onset-detection run (SPEC 9.1)

- `test_detect` (228 RE2 test cases, `--fault-time detect`) finished on `part1-frozen-v2`; run 2 (`test_r2`) started after it.
- Scored with `analysis/part1_tables.py --runs test_r1 --onset test_detect` (`results/part1_onset.csv`) and the new `analysis/onset_paired.py` (`results/part1_onset_paired.csv`, exact McNemar against the given-time run on the same cases).
- AC@1 0.737 with the time detected against 0.855 with it given (10 fixed, 37 broken, p < 0.001); the control, given the true time, scores 0.640 on these cases. Most of the loss is on RE2-SS (0.656 against 0.822, p = 0.006).
- Onset found in 97.8% of cases; median absolute error 69.5 s; 44.3% within 60 s (RE2-OB median 24 s, RE2-TT 122.5 s).
- Thesis: new Sec. "Without the fault time" in Ch. 8; Ch. 10 limitation updated. The other `part1_*.csv` files written by this call use run 1 only and are not committed; they are regenerated after runs 2–3.

## 2026-11-08: repeat runs closed as a limitation (user decision)

- The server has refused SSH logins since 31 Oct (last known: `test_r2` at 32 of 676 cases, `test_r3` not started), so runs 2–3 could not be checked or finished before the thesis goes to the supervisor.
- The user agreed to complete the thesis without them. The two placeholder boxes (Ch. 8 opening, Sec. 9.4.1 D1) are replaced by text pointing to the 34-case rerun and to Sec. 10.3, whose limitation now states that the SPEC's three runs were not completed. No numbers changed.
- Thesis guideline pass also done today (`thesis/GUIDELINES_CHECKLIST.md`): single-spaced captions, figure text at a true 8 pt, certificate clause from the sample page; student signature added (image gitignored).

## 2026-11-08: thesis proofread and restructured (user request: concise, nothing lost)

- Proofread fixes (commit e56f5ee): waves 1–2 numbers in Ch. 9 labelled as such next to the 676-case figures; an unsourced estimate ("roughly 50,000 model calls", from this log) reworded; "user" wording removed; "0 of 37 tools" corrected to "none" (37 counted agent–tool pairs; every tool was used, `p2_tools_census.csv`); RE2-OB "all 24" labelled waves 1–2; RE3 sizes updated to 13–30.
- Restructure: 10 chapters to 9 (OmniRCA and the framework merged). Merged tables: framework questions and analyses; OmniRCA datasets, per-dataset accuracy and strata; overall and strata; fault kind with fault-type accuracy (from the confusion matrix); claim verdicts with "what held up". Removed duplicate visuals: OmniRCA accuracy chart, per-dataset chart, baselines chart (their tables carry the same numbers plus p-values). Agents described in one table. Adapter, statistics and instrumentation moved to the setup chapter; confidence table moved to D2. Appendices C and D merged.
- Checked by script: every number in the old chapters still appears in the new ones, except two confusion-matrix counts (87, 36) that remain as their percentages (77.0%, 31.9%).
- Layout: paragraph gap 5 pt, tighter lists, float placement relaxed so tables sit on text pages. Result: 78 → 67 PDF pages (chapters 56 → 47 pages).

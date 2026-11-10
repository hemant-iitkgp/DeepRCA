# DeepRCA: Test Results

This file is updated after each test wave. Every number comes from a CSV in `results/`, cited next to it. Terms in *italics* are defined in the [Glossary](#glossary).

| Wave | Cases | Status | Source files |
|---|---|---|---|
| 1 | 170 | **Done** (run 1) | `results/wave_w1_r1_*.csv`, `results/paper_compare_w1_r1.csv` |
| 2 | 169 | **Done** (run 1) | `results/wave_w2_r1_*.csv`; waves 1–2 combined: `results/wave_w12_r1_*.csv`, `results/paper_compare_w12_r1.csv` |
| 3 | 169 | Not started | |
| 4 | 168 | Not started | |

Last update: 2026-10-28, after wave 2. Part B onwards reports waves 1–2 combined (339 cases).

---

## Part A. The test bed

### What the system does

Given telemetry from a microservice application where one service has a fault, the system names the faulty service (the *root cause*), then ranks the other suspects below it. A main agent (the LLM) plans the investigation. It sends *sub-agents* to examine each suspicious *span* or service with code tools, asks one sub-agent to test the top suspects, and asks a *critic* to challenge the answer. A code *guardrail* rejects any report that is not backed by saved evidence.

- **Model:** Gemini 3.7 Flash on Vertex AI (`config/models.yaml`).
- **Frozen code:** tag `part1-frozen-v2`, commit `dd73a19`. Nothing changed during the tests.

### The benchmark: RCAEval

RCAEval has 9 datasets: 3 releases (RE1, RE2, RE3) × 3 demo applications, Online Boutique (OB), Sock Shop (SS) and Train Ticket (TT, the largest). Faults were injected on purpose, so the true root cause is known.

| Release | Fault kinds | Data available | Cases (OB / SS / TT) |
|---|---|---|---|
| RE1 | cpu, mem, disk, delay, loss | metrics only | 125 / 125 / 125 |
| RE2 | cpu, mem, disk, socket, delay, loss | metrics + logs; traces for OB and TT only | 90 / 90 / 90 |
| RE3 | code faults (f1–f5) | metrics + logs; traces for OB, TT and 13 of 30 SS cases | 30 / 30 / 30 |

Source: `results/audit_summary.csv`. 735 cases in total.

### Splits and waves

- **Dev split:** 59 cases (RE2-OB and RE3-OB). Used for all tuning.
- **Test split:** the other 676 cases, never used for tuning (`results/test_waves_summary.csv`).
- **Waves:** the test cases are split into 4 waves of about 170 each. Each wave has every dataset in the same proportion, so every wave is a fair small version of the whole test set.

### How we score

- We use RCAEval's own scoring code (*AC@1*, *AC@3*, *Avg@5*), at the service level unless stated otherwise.
- **Comparison point (*control*):** a simple statistical method. It ranks services by how far their metrics jumped from the pre-fault period. It runs on exactly the same cases.
- The fault start time is given to the system, as in RCAEval's own baselines.

---

## Part B. Our results

The headline numbers are for **waves 1 and 2 combined: 339 cases, half the test set, one run** (`results/wave_w12_r1_*.csv`). Per-wave files: `results/wave_w1_r1_*.csv` and `results/wave_w2_r1_*.csv`.

### B.1 Did it run cleanly?

- **Completion:** 337 of 339 cases ended with an accepted report.
  - One RE1-SS case hit the 2-hour limit and gave no answer.
  - One RE1-OB case stopped without submitting a report.
  - Both count as wrong.
- **No crashes, no forced reports.** The guardrail rejected a report twice, in one case, which was then fixed and accepted (`results/wave_w12_r1_process.csv`).
- **Cost:** $0.35 per case, $117.22 in total.
- **Time:** about 14 minutes per case on average.
- **Effort:** 14.5 helpers per case (`results/wave_w12_r1_ops.csv`).

### B.2 Overall

| | AC@1 | AC@3 | AC@5 | Avg@5 |
|---|---|---|---|---|
| **Our system** | **0.729** (95% *CI* 0.681–0.776) | 0.850 | 0.891 | 0.831 |
| Control | 0.596 | 0.805 | — | 0.775 |

- **Case by case:** the system fixed 78 cases the control got wrong and broke 33 it got right. *McNemar* p < 0.001.
- **The two waves agree:** AC@1 was 0.706 in wave 1 and 0.751 in wave 2, against the control's 0.582 and 0.609 (`results/wave_w1_r1_accuracy.csv`, `results/wave_w2_r1_accuracy.csv`).
- **Top 3 has caught up a little:** it was level with the control in wave 1. Over both waves it is 0.850 vs 0.805.

### B.3 Easy vs hard cases

| Case type | Cases | Our system | Control | Fixed | Broken |
|---|---|---|---|---|---|
| ***Misleading*** (the loudest service is a victim) | 137 | **0.569** | 0.000 | 78 | 0 |
| ***Aligned*** (the loudest service is the cause) | 202 | 0.837 | 1.000 | 0 | 33 |

This is the main result. On misleading cases the system finds the real cause in more than half, and has it in the top 3 in 0.781 of them (control 0.518). The cost is 33 easy cases it argued itself away from. The project's claim, "win on misleading cases *without losing* on aligned ones", **does not hold yet**.

### B.4 By dataset

| Dataset | Cases | Ours AC@1 | Control AC@1 | Fixed / Broken | p | Ours AC@3 | Control AC@3 |
|---|---|---|---|---|---|---|---|
| RE1-OB | 63 | **0.857** | 0.667 | 13 / 1 | 0.002 | 0.952 | 0.857 |
| RE1-SS | 63 | 0.825 | 0.762 | 9 / 5 | 0.424 | 0.984 | 0.952 |
| RE1-TT | 62 | 0.306 | **0.484** | 7 / 18 | 0.043 | 0.468 | **0.677** |
| RE2-OB | 24 | **1.000** | 0.792 | 5 / 0 | 0.062 | 1.000 | 0.958 |
| RE2-SS | 44 | 0.864 | 0.750 | 8 / 3 | 0.227 | 0.955 | 0.977 |
| RE2-TT | 46 | **0.848** | 0.391 | 23 / 2 | < 0.001 | 0.891 | 0.587 |
| RE3-OB | 7 | 1.000 | 0.714 | 2 / 0 | 0.500 | 1.000 | 0.857 |
| RE3-SS | 15 | 0.467 | 0.200 | 6 / 2 | 0.289 | 0.800 | 0.267 |
| RE3-TT | 15 | 0.467 | 0.267 | 5 / 2 | 0.453 | 0.733 | 0.933 |

By app: **Online Boutique 0.904** vs 0.702 (p < 0.001), Sock Shop 0.795 vs 0.689 (p = 0.035), Train Ticket 0.528 vs 0.423 (p = 0.111).

**Significant differences:**
- **Better than the control:** RE1-OB and RE2-TT.
- **Worse than the control:** RE1-TT, the large app with metrics only.

### B.5 By fault kind

| Fault kind | Cases | Ours | Control | p |
|---|---|---|---|---|
| socket | 19 | **1.000** | 0.632 | 0.016 |
| memory | 57 | 0.895 | 0.807 | 0.267 |
| cpu | 57 | **0.754** | 0.544 | 0.008 |
| disk | 56 | 0.750 | **0.804** | 0.629 |
| delay | 56 | 0.714 | 0.554 | 0.122 |
| code | 37 | **0.568** | 0.324 | 0.049 |
| loss | 57 | 0.544 | 0.439 | 0.146 |

AC@1. Disk is the only kind where the control is ahead.

### B.6 The other outputs

**Fault kind: correct in 0.413 of cases** (`results/wave_w12_r1_faulttype.csv`). What the system answered, by true kind (`results/wave_w12_r1_faulttype_confusion.csv`):

| True kind ↓ / answered → | cpu | memory | disk | socket | delay | loss | code | unknown | Correct |
|---|---|---|---|---|---|---|---|---|---|
| cpu (57) | **46** | 6 | 1 | 0 | 4 | 0 | 0 | 0 | 80.7% |
| memory (57) | 9 | **38** | 5 | 0 | 5 | 0 | 0 | 0 | 66.7% |
| disk (56) | 18 | 16 | **19** | 0 | 2 | 0 | 0 | 1 | 33.9% |
| socket (19) | 17 | 0 | 1 | **0** | 1 | 0 | 0 | 0 | 0% |
| delay (56) | 11 | 9 | 3 | 0 | **33** | 0 | 0 | 0 | 58.9% |
| loss (57) | 12 | 11 | 0 | 1 | 32 | **0** | 0 | 1 | 0% |
| code (37) | 14 | 12 | 3 | 0 | 4 | 0 | **4** | 0 | 10.8% |

- **Never answered "loss",** in 339 cases. Loss faults are mostly called "delay".
- **"cpu" is the default guess:** it was the answer in 127 cases, and right in only 36.2% of those.
- **Socket faults** were called "cpu" in 17 of 19 cases.
- **Code faults** were named correctly in 4 of 37 cases.
- **Depends on the service:** 48.6% correct when the top service is right, 21.7% when it is wrong.

**Indicator (service + metric): correct at #1 in 0.460 of cases.** That covers 302 cases; code faults have no RCAEval indicator.
- **Best:** memory 0.667, cpu 0.649.
- **Worst:** disk 0.143, socket 0.000, RE1-TT 0.145.

**Confidence: honest on average, weak at telling right from wrong** (`results/wave_w12_r1_confidence.csv`).

| Confidence given | Cases | Actually right (AC@1) |
|---|---|---|
| below 0.60 | 41 | 0.585 |
| 0.60–0.65 | 126 | 0.683 |
| 0.65–0.70 | 99 | 0.707 |
| 0.70–0.80 | 32 | 0.875 |
| 0.80–1.00 | 41 | 0.951 |

- **Well matched on average:** mean confidence 0.686 against AC@1 0.729. Higher scores are right more often.
- **Weak at separating right from wrong:** *AUROC* 0.634, and most answers land between 0.60 and 0.70. Right answers average 0.699; wrong ones 0.650.

**Gate (V4):** never applied, because it is off, so V4 = V3.

---

## Part C. Comparison with the RCAEval paper

The RCAEval paper (arXiv:2412.17015) reports baselines for **one dataset only: RE2-TT**, per fault kind, at the service level. Its table is copied as published (`results/rcaeval_paper_re2tt.csv`). Ours covers the 46 RE2-TT cases in waves 1–2, averaged over fault kinds the same way the paper does (`results/paper_compare_w12_r1.csv`).

**RE2-TT, average over fault kinds:**

| Method | Data used | Cases | AC@1 | AC@3 | Avg@5 |
|---|---|---|---|---|---|
| **Our system** | metrics, logs, traces | 46 | **0.842** | **0.884** | **0.876** |
| BARO (multi-source) | metrics, logs, traces | 90 | 0.690 | 0.820 | 0.810 |
| BARO | metrics | 90 | 0.670 | 0.820 | 0.800 |
| TraceRCA | traces | 90 | 0.660 | 0.790 | 0.770 |
| PDiagnose | metrics, logs, traces | 90 | 0.480 | 0.700 | 0.670 |
| Our control | metrics | 46 | 0.402 | 0.589 | 0.562 |
| CIRCA | metrics | 90 | 0.320 | 0.470 | 0.460 |
| CausalRCA | metrics | 90 | 0.220 | 0.470 | 0.430 |
| MicroRank | traces | 90 | 0.160 | 0.370 | 0.310 |
| RCD (multi-source) | metrics, logs, traces | 90 | 0.100 | 0.640 | 0.540 |
| MicroCause | metrics | 90 | 0.100 | 0.220 | 0.200 |
| RCD | metrics | 90 | 0.090 | 0.130 | 0.130 |
| CIRCA (multi-source) | metrics, logs, traces | 90 | 0.060 | 0.110 | 0.130 |

**RE2-TT by fault kind** (AC@1; ours has 7–8 cases per kind, the paper 15):

| Fault | Ours | BARO (multi-source) | TraceRCA | PDiagnose |
|---|---|---|---|---|
| cpu | 0.75 | 0.47 | 0.64 | 0.60 |
| mem | 0.88 | 0.93 | 0.63 | 0.40 |
| disk | 0.86 | 1.00 | 0.64 | 0.33 |
| socket | 1.00 | 0.60 | 0.60 | 0.33 |
| delay | 1.00 | 0.47 | 0.85 | 0.87 |
| loss | **0.57** | 0.67 | 0.57 | 0.33 |

**What this shows:**

- **Our system now leads on all three measures.** In wave 1 it led only on AC@1.
- **The lead is firmer than in wave 1.** Our 95% CI for AC@1 on RE2-TT is 0.739–0.935 (`results/wave_w12_r1_accuracy.csv`); its lower end is above BARO's 0.690. These are still copied numbers on different case counts, so this is strong but not a formal test.
- **The sample is not easy.** Our control scores 0.391 on these cases (`results/wave_w12_r1_accuracy.csv`) and 0.467 on all 90 RE2-TT cases (`results/control_summary.csv`).
- **Part 2 will make it fair:** it re-runs these methods on exactly the same cases.

---

## Part D. Where we lead, where we lag, and why

### Where the system gives an advantage

1. **Misleading cases (0.569 vs 0.000; 78 fixed, none broken).** A failing service makes its callers look bad. The system follows the waiting down to the deepest service that is itself abnormal, instead of blaming the loudest one.
2. **Data with traces (RE2-OB 1.000, RE2-TT 0.848).** Own time and edge gaps separate "I am broken" from "I am waiting". On RE2-TT it beats every method in the RCAEval paper.
3. **cpu, socket and code faults** (all significantly better than the control) **and delay.** These leave clear marks on the faulty service or its links.
4. **It runs reliably.** 337 of 339 cases ended with an evidence-backed report, with no crashes and no forced reports.

### Where the system lags

1. **RE1-TT, the large app with metrics only (0.306 vs 0.484; top 3 0.468 vs 0.677; p = 0.043).** The only dataset where it is significantly worse.
   - *Likely why:* without traces it investigates at most 12 abnormal services (`config/system.yaml`, `max_service_items`). Train Ticket has many noisy services, so the true cause can miss that list, or a neighbour gets picked. The control ranks every service.
2. **Easy (aligned) cases: 33 broken.**
   - *Likely why:* the agent is built to doubt the loudest service. Sometimes it builds a believable caller-or-callee story and moves the blame away from the real cause. The gate (V4) was designed for this, but dev gave nothing to set it on, so it is off.
3. **Packet loss (0.544) and disk (0.750 vs control 0.804).**
   - *Likely why:* loss shows up as retries and time-outs in the callers, so the evidence points at the wrong service. A disk fault makes the faulty service's own metrics jump clearly, which suits the control's simple rule.
4. **Code faults on Sock Shop and Train Ticket (both 0.467).**
   - *Likely why:* code bugs look like ordinary slowdowns, and logs cannot be tied to a request. Only 15 cases each, so these numbers are rough.
5. **Fault kind (0.413) and indicator (0.460).**
   - It never answers "loss", calls socket faults "cpu", and rarely names code faults.
   - *Likely why:* the system is built to find *where*, not *what*. The fault-kind tool (`rca/tools/faults.py`) ranks by raw z-score, so a cpu metric that jumps as a side effect wins. It suggests "loss" only from dropped-packet or error signals, while packet loss mostly shows up as slow calls, which the tool reads as delay.
6. **The confidence score barely separates right from wrong** (AUROC 0.634), although its average level is honest.

### Caveats

- One run on half the test set. Runs 2–3 will show how much answers vary from run to run.
- Datasets with fewer than about 20 cases (RE3) are rough.
- The paper comparison covers one dataset and uses copied numbers.
- The fault start time is given, as for every RCAEval method.

---

## Glossary

- **RCA (root cause analysis):** finding which component caused a failure.
- **Microservice application:** an app built from many small services that call each other over the network.
- **Root cause:** the service where the fault was injected.
- **Metric / log / trace:** a metric is a number over time (CPU, latency…). A log is a text line written by a service. A trace records one user request as it passes through services.
- **Span:** one step of a trace: one service handling one call, with its duration.
- **Sub-agent:** a separate LLM worker that the main agent sends to examine one item and report back.
- **Critic:** a sub-agent that tries to find holes in the proposed answer.
- **Guardrail:** a code check that rejects a final report not backed by saved evidence.
- **AC@k:** the share of cases where the true root cause is in the top k of the ranked list. AC@1 means it was ranked first.
- **Avg@5:** the average of AC@1 to AC@5; one number for the quality of the whole top-5 list.
- **Control:** our statistical comparison point. It ranks services by their largest metric jump (z-score) against the 10 minutes before the fault.
- **z-score:** how many standard deviations a value is from its normal (pre-fault) level.
- **Aligned / misleading case:** aligned means the control's top service is the true cause. Misleading means it is not, because the loudest service is a victim.
- **95% CI (confidence interval):** the range the true accuracy probably lies in, given the number of cases (bootstrap over cases).
- **McNemar test:** a test of whether two methods differ on the same cases; it looks only at the cases where they disagree. A small p (below 0.05) means the difference is unlikely to be luck.
- **V3 / V4:** V3 is the system's own answer. V4 adds a *gate* that keeps the control's answer when one service is clearly the most anomalous. The gate was off in these tests.
- **Indicator:** a service plus the metric that shows the fault (for example, a service's cpu).
- **Confidence score:** a number from 0 to 1 the system attaches to its answer, computed by code from the evidence.
- **AUROC:** how well a score separates right answers from wrong ones. 0.5 is a coin flip, 1.0 is perfect.
- **Confusion matrix:** a table of true kind against answered kind; the diagonal holds the correct answers.
- **BARO, TraceRCA, PDiagnose, CIRCA, RCD, CausalRCA, MicroCause, MicroRank:** published RCA methods evaluated in the RCAEval paper. They are statistical, causal-graph or trace-graph methods, and none uses an LLM.
- **Dev / test split:** dev cases are used to tune the system; test cases are only used to measure it.
- **Frozen:** the code is locked at a fixed commit before testing, so the test cannot influence it.

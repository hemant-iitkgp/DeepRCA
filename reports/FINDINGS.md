# DeepRCA: Part 2 Findings

**Status:** complete, 2026-10-30. All Phase 6–8 runs are finished; no section is pending.

**Scope:**
- **Case set:** the 339 test cases of waves 1–2, one run of the frozen system (`part1-frozen-v2`, commit dd73a19, Gemini 3.7 Flash). Ablations use the 100-case sample (`results/p2_variants_summary.csv`).
- **"Unseen" apps:** Sock Shop and Train Ticket (RE1/RE2/RE3 × SS/TT, 245 cases). DeepRCA was tuned only on Online Boutique dev cases.
- **OmniRCA:** values are transcribed from the user's report "OmniRCA Under Test" (88 held-out cases, GPT-4o). It was not re-run, so its cases, model and control differ from ours. The OmniRCA columns are **indicative only, never a paired test** (`results/p2_omnirca_compare.csv`).
- **RCLAgent:** not run (user decision); its published RE2-OB numbers are transcribed (arXiv:2605.14866v1, Table I).
- **Sources:** every DeepRCA number comes from a CSV in `results/`, cited in each section.

---

## Summary

1. **DeepRCA beats the statistics; OmniRCA did not.** DeepRCA scores 72.9% at #1 against the control's 59.6% (78 fixed, 33 broken, p < 0.001). OmniRCA scored 65.9% against 70.5% (6 / 10, p = 0.455).
2. **It holds on apps it never saw.** On the 245 unseen cases DeepRCA scores 66.1% against the control's 55.5%. On the same cases it leads all nine RCAEval baselines; eight of the nine leads are significant, PDiagnose's is not (C2).
3. **The gain comes from the cases that need reasoning.** On misleading cases DeepRCA is right in 56.9% of 137 cases; the control is right in none by definition. OmniRCA scored 37.5% on 16 such cases.
4. **Both damage easy cases.** DeepRCA broke 33 of 202 aligned cases; OmniRCA broke 10 of 72. This is the main open weakness.
5. **It rejects baseless planted leads.** 0 of 40 implausible planted suspects were accepted (OmniRCA: 9 of 20 before its fix). Believable wrong leads got through 5 of 40 times (A2).
6. **No single part decides.** OmniRCA's first agent fixed the answer in 82% of cases. In DeepRCA, the main agent overrode the plain evidence count in 184 cases, fixing 121 answers and breaking 4.
7. **DeepRCA's evidence can argue against a suspect; OmniRCA's never did.** 164 findings cleared their suspect and 215 hypotheses were refuted. OmniRCA had 0 of 329 items arguing against.
8. **The suspect list is the bottleneck.** In 61 of the 92 wrong answers the true cause was never on the code suspect list; when it was, the agent picked it 87.8% of the time (C5).
9. **Quoted numbers are faithful.** 99.7% of the numbers in DeepRCA's findings match the data (OmniRCA: 43 of 43 values correct, but 7 of 8 "z-scores" mislabelled).

---

## Theme A: How it decides

### A1. Who decides the answer
Source: `results/p2_a1_summary.csv`.

| | OmniRCA | DeepRCA |
|---|---|---|
| Main originator of the final answer | first agent, 82% | investigators 37.8%, main agent 31.0%, code tools 17.7%, testers 13.0%, critic 0.6% |
| Effect of the later components | five agents net +3 cases over 72 runs | main agent's first draft overrides the code evidence leader in 184 cases: 121 fixed, 4 broken |

The code evidence leader is the service blamed by the most findings, weighted by their confidence. When the main agent overrode it, that leader alone was right in only 9.8% of cases. So DeepRCA's gain comes from reasoning over the findings, not from counting them.

### A2. Planted false leads
Source: `results/p2_a2_summary.csv`, 20 cases per arm.

| Planted lead | Implausible (least anomalous service) | Plausible (anomalous, not the cause) |
|---|---|---|
| Fake flagged span on that service | 0 of 20 accepted; true cause found 19 of 20 | 1 of 20 accepted; true cause found 19 of 20 |
| That service put first in `candidate_rank` | 0 of 20 accepted; true cause found 18 of 20 | 4 of 20 accepted; true cause found 15 of 20 |
| **Both** | **0 of 40** accepted; 37 of 40 found | **5 of 40** accepted; 34 of 40 found |
| OmniRCA (first agent's answer replaced) | 9 of 20 before its fix, 0 of 20 after | 5 of 20 before, 3 of 20 after |

The guardrail rejected none of these reports: the agent dropped the baseless leads itself. Believable leads in the statistical ranking are the one weak spot (4 of 20).

### A2.4. Does the evidence ever argue against a suspect?
Source: `results/p2_a24_summary.csv`.

| | OmniRCA | DeepRCA |
|---|---|---|
| Items arguing against a suspect | 0 of 329 | 164 of 3,306 findings clear their suspect (5.0%); 13.7% carry a real counter-observation; 215 of 1,166 hypotheses refuted (18.4%) |

**A defect found:** 84.2% of hypothesis-tester answers carry no evidence-for items at all. The testers give verdicts without saved proof, so their verdicts are weakly grounded.

### Suspect elimination
Source: `results/p2_elimination_summary.csv`.
- **Decision level:** of 2,913 suspect entries that were not the cause, 2,815 (96.6%) were not ranked #1. Of 326 entries that were the cause, 43 (13.2%) were not ranked #1.
- **Finding level:** findings cleared 284 of 2,844 non-cause entries (10.0%) and wrongly cleared 52 of 462 true-cause entries (11.3%). Clearing happens mostly on datasets with traces.

---

## Theme B: What it can and cannot diagnose

### B1. Source or loudest symptom
Source: `results/wave_w12_r1_accuracy.csv`.

| Case type | OmniRCA (system vs control) | DeepRCA (system vs control) |
|---|---|---|
| Misleading | 37.5% vs 12.5% (n = 16), p = 0.125 | **56.9% vs 0% (n = 137)**, 78 fixed, 0 broken |
| Aligned | 72.2% vs 83.3% (n = 72), 10 broken, p = 0.039 | 83.7% vs 100% (n = 202), 33 broken |

OmniRCA's control shows 12.5% on misleading cases, while ours is 0% by definition. The two splits were therefore drawn from different control runs.

### B2. By fault kind
Source: `results/wave_w12_r1_accuracy.csv`.
- **Significantly better than the control:** socket 100%, cpu 75.4%, code 56.8%.
- **The control is ahead:** disk only, 80.4% vs 75.0%.
- **Fault-type naming:** DeepRCA 41.3% correct (`results/wave_w12_r1_faulttype.csv`); OmniRCA 10–30%. Both are weak. DeepRCA never answers "loss" and calls socket faults "cpu".

### B3. Error taxonomy
Source: `results/p2_b3_summary.csv`, 92 wrong answers.

| Role of the wrongly blamed service | OmniRCA | DeepRCA |
|---|---|---|
| Upstream caller or entry point | 23 of 30 (77%) | 9 of 92 (10%) |
| Unrelated (no call path) | – | 39 (42%), 37 of them on Train Ticket, median 3 hops away |
| No call graph (Sock Shop) | – | 25 (27%) |
| Sibling / downstream | 1 of 30 | 10 / 9 |

### B4. What predicts failure
Source: `results/p2_b4_predictors.csv`.
- **Crowding:** success correlates with the number of anomalous services at r = −0.33 (OmniRCA: −0.34).
- **Confounded with size:** the correlation with the number of services is the same, r = −0.33, so crowding and app size cannot be separated here.
- **Margin:** the lead of the control's #1 over its #2 predicts the control (r = 0.30) but not DeepRCA (r = 0.01).

---

## Theme C: What drives the numbers

### C1. Ablation ladder
Source: `results/p2_variants_summary.csv`. Each variant changes one thing and runs on the same cases as normal DeepRCA (V3); paired, exact McNemar.

| Variant | Cases | Variant AC@1 | V3 AC@1 | Fixed / broken | p |
|---|---|---|---|---|---|
| Smaller model | 100 | 57.0% | 69.0% | 6 / 18 | 0.023 |
| Traces off | 27 | 48.1% | 77.8% | 4 / 12 | 0.077 |
| No guardrail | 100 | 72.0% | 69.0% | 8 / 5 | 0.58 |
| Fixed code loop instead of agent-driven loop | 100 | 70.0% | 69.0% | 10 / 9 | 1.0 |
| No critic | 100 | 68.0% | 69.0% | 7 / 8 | 1.0 |

- Only the smaller model differs significantly from V3. The guardrail, critic and agent-driven loop do not change accuracy; the guardrail's measured value is robustness (A2).
- OmniRCA deferred its own ladder, so there is no counterpart.

### C2. Against statistics and published baselines
Sources: `results/p2_unseen_baselines.csv`, `results/p2_unseen_systems.csv`, `results/rclagent_compare_w12_r1.csv`, `results/rclagent_lift_w12_r1.csv`, `results/baselines_gaps.csv`.

**RCAEval baselines, unseen apps only, same cases.** Each baseline runs unchanged through RCAEval and is compared with DeepRCA on exactly the cases it answered (its own crashes left out):

| Baseline | Cases | Baseline AC@1 | DeepRCA AC@1 | Fixed / broken | p |
|---|---|---|---|---|---|
| PDiagnose | 46 | 69.6 | 78.3 | 8 / 4 | 0.388 |
| TraceRCA | 46 | 52.2 | 78.3 | 16 / 4 | 0.012 |
| CIRCA | 243 | 38.3 | 65.8 | 89 / 22 | < 0.001 |
| Multi-source BARO | 89 | 38.2 | 85.4 | 46 / 4 | < 0.001 |
| Multi-source CIRCA | 90 | 37.8 | 85.6 | 47 / 4 | < 0.001 |
| Multi-source RCD | 90 | 33.3 | 85.6 | 52 / 5 | < 0.001 |
| BARO | 243 | 26.7 | 65.8 | 112 / 17 | < 0.001 |
| MicroRank | 40 | 20.0 | 85.0 | 28 / 2 | < 0.001 |
| RCD | 243 | 18.9 | 65.8 | 120 / 6 | < 0.001 |

- Counting a baseline's crash as a miss (RCAEval's rule), DeepRCA beats all nine with p ≤ 0.002; PDiagnose then scores 47.8 against 71.6 on 67 cases.
- At AC@3 the gap narrows: multi-source BARO 87.6 against DeepRCA 92.1. DeepRCA's advantage is mainly the #1 answer.
- **Phase 6 gate:** every case without a ranking has a recorded reason (`results/baselines_gaps.csv`). TraceRCA, PDiagnose and MicroRank crash inside RCAEval's code when a fault-period operation never appeared in the normal period (KeyError in `tracerca.py`); MicroRank also fails on RE3-SS (empty array); multi-source BARO crashes on one RE2-TT case (empty array in `mmnsigma`); RCAEval's `main.py` cannot parse one RE3-TT folder name, so BARO, CIRCA and RCD never see its 2 cases. Multi-source methods have no RE3 input files and run on RE2 only.

**Agent systems, each against its own statistical baseline** (different cases and models, indicative):

| System | Data | AC@1 | Own baseline | Gain |
|---|---|---|---|---|
| DeepRCA | RE2-TT (unseen) | 84.8 | control 39.1 | +45.7 |
| DeepRCA | RE2-SS + RE2-TT (unseen) | 85.6 | control 56.7 | +28.9 |
| DeepRCA | all 6 unseen datasets | 66.1 | control 55.5 | +10.6 |
| OmniRCA | RE2-TT | 42.9 | control 60.7 | −17.9 |
| RCLAgent (Claude-3.5-Sonnet, paper) | RE2-OB | 52.3 | its BARO 18.9 | +33.4 |

- DeepRCA's own RE2-OB score (100%, 24 of 24) is an upper bound: Online Boutique is its tuning app.
- Against the RCAEval paper's published numbers (RE2-TT only, copied, not re-run): DeepRCA 0.842 vs best baseline 0.690 at AC@1 (`results/paper_compare_w12_r1.csv`).

### C3. Validity probes
Source: `results/p2_variants_summary.csv`.
- **Prompt stripped to a bare case ID:** not needed. DeepRCA's start message already carries only the case ID, data types and window, with no symptom text.
- **Hidden names:** with every service name replaced, DeepRCA scores 77.8% on 27 cases, the same as with names (1 fixed, 1 broken). The model is not recalling the benchmark apps. OmniRCA scored 9 of 10 either way, but its name-keyed safeguards stopped working; DeepRCA has no name-keyed rules by design.

### C4. Faithfulness
Source: `results/p2_c4_summary.csv`.
- 9,957 of 9,987 checked numeric claims in findings match code recomputation within 5% (99.7%).
- Most of the 30 non-matches are machine-level metrics, which the checker does not recompute.
- OmniRCA's prose called a composite score a "z-score" in 7 of 8 cases. DeepRCA's tools report only true z-scores under that name.

### C5. Code-flagged suspects vs the agent's answer
Sources: `results/p2_c5_summary.csv`, `results/p2_c5_by_fault.csv`, `results/p2_c5_cases.csv`.
- **Overall:** code put the true cause on the suspect list in 75.2% of cases. When it did, the agent picked it in 87.8% (224 of 255). Of the 92 wrong answers, 61 had the cause missing from the list; 31 had it on the list.
- **By source of the suspects:** only 81 cases got their suspects from traces (RE1 and the Sock Shop sets have no trace file); 246 used metric anomalies; 12 got no suspects at all. The true cause was on the list in 77.8% of trace cases and 78.0% of metric cases.
- **What traces miss:** faults that barely change timing or errors. Among trace cases, code faults f2 (0 of 3) and f4 (2 of 6) and packet loss (4 of 6) were caught least; delay (11 of 12), memory (11 of 12) and socket (8 of 8) best.
- **RE1-TT:** code put the true cause on the list in only 21.0% of cases, which explains DeepRCA's weakest dataset.

### Instruction compliance and tool use
Source: `results/p2_compliance_summary.csv`, `results/p2_tools_census.csv`.

| | OmniRCA | DeepRCA |
|---|---|---|
| Prompt-rule compliance | 69.8–100%; "for each of N" rules fail | 98.8–99.7% for every rule but one; "for each" rules are enforced in code |
| Tools never called | 7 of 24 | none |

The one exception: on cases without traces, the agent first tries the trace tool in 88% of them, then uses the right one. It costs one wasted call.

---

## Theme D: Cross-cutting

### D1. Stability
Source: `results/p2_variants_summary.csv` (`p2_rerun`).
- 34 cases run a second time: 61.8% against 67.6% in the first run (0 fixed, 2 broken, p = 0.5).
- The #1 answer was the same in 82.4% of cases, so about one answer in six changes on a rerun. OmniRCA: 80%, 80%, 70% on identical reruns, with 17% of answers changing.
- Differences of a few cases between single runs are noise; every comparison here is paired.

### D2. Calibration
Source: `results/p2_d2_calibration.csv`.
- **Overall:** mean confidence 0.686 against AC@1 0.729; AUROC 0.634.
- **Too low** on Online Boutique (gap −0.20) and Sock Shop (−0.13).
- **Too high** on Train Ticket (+0.17; RE1-TT +0.34).
- **OmniRCA's comparison:** its HIGH label was right 90% of the time on synthetic data and 48% on Train Ticket.

---

## Theme E: New for this system

- **E1, cost and time:** $0.35 and about 14 minutes per case (`results/wave_w12_r1_ops.csv`). The smaller model costs $0.09 and 2.8 minutes per case (`results/p2_variants_summary.csv`). Baseline run times were not recorded per case, so no timing comparison is made.
- **E3, missing data types:** RE1 has metrics only. It scores 85.7% (OB), 82.5% (SS) and 30.6% (TT) (`results/wave_w12_r1_accuracy.csv`). With traces switched off on 27 trace cases, accuracy falls from 77.8% to 48.1% (4 fixed, 12 broken, p = 0.077).
- **E4, transfer:** the frozen system was tuned only on Online Boutique dev cases. On Sock Shop it scores 79.5% and on Train Ticket 52.8%, against Online Boutique's 90.4% (`results/wave_w12_r1_accuracy.csv`).
- **E5, model size:** the smaller model scores 57.0% against 69.0% on the same 100 cases (6 fixed, 18 broken, p = 0.023), and is worse on aligned cases (65.4% vs 80.8%, p = 0.039). OmniRCA's smaller model also fell below the statistical control on real data.

---

## Limits

- **One run on half the test set.** Waves 3–4 and full repeat runs were deferred; the stability rerun covers only 34 cases.
- **Ablations on a 100-case sample;** traces-off and hidden names on 27 cases each.
- **OmniRCA's numbers are transcribed, not re-run.** Different cases, model and control; indicative only.
- **RCLAgent was not run** (user decision); its numbers are its paper's, on RE2-OB only.
- **Some baselines crash on part of the data inside RCAEval's code;** both ways of counting are reported.
- **MicroCause and CausalRCA were not run.** MicroCause fails inside RCAEval; CausalRCA is too slow on the shared server.
- **The fault start time is given,** as in every RCAEval method.

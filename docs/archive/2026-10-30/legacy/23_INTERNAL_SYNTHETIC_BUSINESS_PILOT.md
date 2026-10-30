# RetailIQ — Internal Synthetic-Data Business Pilot

**Purpose:** run an **exploratory classroom simulation** of RetailIQ's three hypotheses: **Faster** (shorter correct task completion), **Easier** (less navigation/effort, better user-perceived ease) and **Reliable** (correct, traceable answers). The **existing instrument directly measures only task time, correctness and optional manual steps**. Structured ease-of-use score and genuine multi-tool POS/WMS comparisons **are not implemented**, so this pilot cannot yet validate all three dimensions or prove real-store productivity, time savings or ROI.

**Capacity:** four volunteer participants (P01–P04) plus one facilitator from the five-person project team; approximately 15–25 minutes per participant including instruction, within course availability. Do **not** fabricate observations if the team cannot run the pilot. **Manual** means a human operating existing software (reports, filters, CSV/Excel/BI/ERP), not computing without software; CSV/Excel here is only a convenient simulated proxy for tools in a real retailer.

## What already exists

- Main RetailIQ synthetic seed: **10 products, three locations, 120 orders**, as-of **2026-10-28**.
- scripts/business_pilot_export.py exports three manual input files and balanced task assignments; it builds a separate facilitator truth key using read-only SQLite queries.
- scripts/business_pilot_analyze.py returns NOT_MEASURED for blank sheets, INCOMPLETE for partial records, and only **descriptive exploratory** results after all 24 trials are recorded. The current report calculates **median duration for correct trials**, which is *not* an all-attempt task-time statistic; accuracy and omitted/failed cases must always be reported jointly.
- tests/test_business_pilot.py verifies export, answer-key arithmetic, allocation balance and anti-fabrication behavior. Test timing numbers inside unit tests are expressly invented solely to test arithmetic.
- .github/workflows/business-pilot.yml generates two downloadable GitHub Actions artifacts: **participant pack** and separately **facilitator answer key**. The answer-key artifact is visible to anyone with access to GitHub Actions for this repo; do not share it with volunteers until scoring is complete.

## Prepare

Run on a clean local checkout with Python 3.11+:

~~~bash
python -m scripts.seed
python -m scripts.business_pilot_export --db data/retailiq.sqlite3 --output data/business_pilot_run1 --as-of 2026-10-28
python -m scripts.business_pilot_analyze --folder data/business_pilot_run1
~~~

The last command should say NOT_MEASURED, with **0 recorded trials**. No efficiency improvement is calculated.

Or download the generated **participant pack** from the GitHub Actions run named "RetailIQ synthetic business pilot pack". Do not send the facilitator answer key to volunteers.

Files produced in the output folder:

| File | Who gets it | Purpose |
|---|---|---|
| products.csv | Volunteers doing manual tasks | SKU/name/specification lookup |
| inventory.csv | Volunteers doing manual tasks | On-hand, reserved and location details |
| sales.csv | Volunteers doing manual tasks | Order IDs, status, date, SKU, unit price, discount and quantity in one view |
| assignments_and_results.csv | Facilitator; filtered per participant | Balanced task schedule and blank response/time/correctness fields |
| FACILITATOR_ONLY_answer_key.csv | **Facilitator only** | Independent numeric expected outputs by task ID |
| manifest.json | Facilitator | Fixture SHA-256, reference month, count and explicit synthetic-data label |

The exporter refuses to overwrite an existing folder, to protect any measurements already collected. Use a new run directory for a new pilot. Never export confidential business/customer data.

## Six participant tasks

| Task | Exact question asked in both methods | Expected information |
|---|---|---|
| T01 | How many units of AlphaBook Pro 14 are currently in stock? | SKU, total, location breakdown |
| T02 | How many units of NovaPhone X are currently in stock? | SKU, total, location breakdown |
| T03 | How many units of USB-C GaN Charger 65W are currently in stock? | SKU, total, location breakdown |
| T04 | What is the revenue this month? | Reference month, net total VND, channel breakdown |
| T05 | Which products are top sellers? | Top five SKUs ranked by completed units sold |
| T06 | Which top seller needs a replenishment review based on stock? | Same verified SKU, units sold, available total, review flag and limitations |

**Fairness:** Each of four volunteers sees every task **once**: three assigned to manual and three assigned to retailiq. For each task, exactly two people use each method, with different task orders. Do not let a participant solve the same question twice to avoid answer memorization. Four volunteers are a convenience sample, **not statistical evidence**. This exercise tests fixed single-turn questions, **not the target multi-turn contextual experience**; separately design a follow-up test once context handling is ready.

## Facilitation instructions

1. Use the **same seeded reference month (2026-10)** and unchanged source files for everyone.
2. Manual condition: allow normal CSV/Excel filtering, sorting, pivoting and arithmetic; do not allow assistant/chatbot help. The human performs the steps on existing tools; CSV/Excel **stands in for**, but does not reproduce, real multi-screen POS/BI/ERP/WMS workflows. For T06 apply the published teaching heuristic: **REVIEW iff total available < monthly completed units sold**.
3. RetailIQ condition: start the local app from the same seed with RETAILIQ_MODE=offline. Each question is entered independently with no prior conversation state. If using full mode instead, use a separate pilot and identify that changed condition; the original pilot specifically measures offline deterministic support.
4. Both conditions start with file/app already open. Timer starts **when the participant receives the question**, ends after they record the final answer and reasoning, **including reading and checking the evidence**.
5. Facilitator marks correct as 1 **only** if all listed required fields and the business decision agree with the separate answer key; otherwise 0. Do not count just receiving HTTP 200 as a correct decision. Record the participant's actual answer in answer_recorded, elapsed positive seconds in duration_seconds, optional manual_steps (count human interactions such as filters/lookups/calculations for either method) and usability comments in notes. Record any clarification, correction or retry in notes; the current analysis script does **not** calculate an all-attempt or retry-adjusted task-time metric.
6. Use pseudonymous P01–P04. Do not record names, API keys, customer information or confidential input. Copy each participant's rows into the master CSV without altering assignment columns. Do not expose the facilitator key to participants.

## Missing UX instrument and next iteration

The present CSV schema is fixed and is validated strictly by the analyzer. It **does not contain an ease-of-use score or separate clicks/tool-switch counts**. Do not add columns to the existing sheet and imply the analyzer processes them. In a *future instrument revision*, capture a post-task **1–5 Ease-of-Use Rating**, clicks/filters/screen switches and retries/clarifications. Define the 1–5 anchors (1 very difficult; 5 very easy), and update exporter, analyzer and tests together. The current notes field can preserve qualitative impressions, but **cannot substitute for a structured quantitative ease measure**.

For a more realistic later comparison, reproduce a fixed manual workflow across representative local mock POS/BI and WMS views; measure the *same end-to-end task* and include failure/retry attempts rather than relying on correct-only medians. This is future work, not evidence from this study.

## Analysis

Once the CSV has actual observations, run:

~~~bash
python -m scripts.business_pilot_analyze --folder data/business_pilot_run1 --output data/business_pilot_run1/summary.json
~~~

**Blank:** NOT_MEASURED, no efficiency metric. **Partial:** INCOMPLETE, number of missing observations and **no** efficiency claim. **All 24 complete:** COMPLETE_EXPLORATORY, correctness rate and median time **for correct answers** by method; additional per-task descriptive summaries and an illustrative time difference only if both method medians exist. **These metrics do not yet establish Easier or general time-to-insight reduction**, because ease score, retries and actual tool-switch comparisons are not measured.

The computed percentage, if any, describes **these four volunteers and this synthetic dataset**. It is not an estimate of financial savings, production agent quality, real user impact, causality or statistical significance. **Always report answer correctness alongside time; a faster wrong answer is not success.** Small samples and different task difficulty restrict conclusions.

## Report narrative (after observations exist)

- Context: internal synthetic inventory & sales decision-support pilot; source month 2026-10.
- Method: four volunteers, 24 counterbalanced task trials, manual CSV versus offline RetailIQ; fixed six prompts.
- Accuracy first: correct tasks out of 12 per method, plus any major incorrect decisions.
- Completion times: descriptive medians and per-task breakdowns of **correct-only trials** with successful-trial counts; separately report correctness/failure and any known retries; do not equate the medians with all-attempt time-to-insight.
- Qualitative notes: which CSV steps were tedious, UI issues, missing freshness evidence and user feedback.
- Limits: no real retailer, no generalization, no business ROI, no controlled random sample.
- Next decision: retain narrow scope or address a high-impact usability issue before adding more agent functionality.

**Do not present any numerical “time saved,” “productivity gain,” “ease-of-use improvement” or “business ROI” until the relevant actual observations are captured and verified.** The existing tool reports only exploratory synthetic-data timings and accuracy, never a verified retailer benefit.

Related: [Selected Business Problem](21_INVENTORY_SALES_BUSINESS_SCOPE.md), [Golden Business Scenarios](22_BUSINESS_GOLDEN_SCENARIOS.md), [Technical E2E & Benchmark](20_LOCAL_E2E_BENCHMARK_EVIDENCE.md).

# RetailIQ — Internal Synthetic-Data Business Pilot

**Purpose:** explore whether RetailIQ helps team volunteers complete inventory and sales tasks faster and as correctly as a manual CSV-based workflow. **This is a controlled classroom simulation**, not evidence of real-store productivity or a validated ROI.

**Capacity:** four volunteer participants (P01–P04) plus one facilitator from the five-person project team; approximately 15–25 minutes per participant including instruction, within course availability. Do **not** fabricate observations if the team cannot run the pilot.

## What already exists

- Main RetailIQ synthetic seed: **10 products, three locations, 120 orders**, as-of **2026-10-28**.
- scripts/business_pilot_export.py exports three manual input files and balanced task assignments; it builds a separate facilitator truth key using read-only SQLite queries.
- scripts/business_pilot_analyze.py returns NOT_MEASURED for blank sheets, INCOMPLETE for partial records, and only **descriptive exploratory** results after all 24 trials are recorded.
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

**Fairness:** Each of four volunteers sees every task **once**: three assigned to manual and three assigned to retailiq. For each task, exactly two people use each method, with different task orders. Do not let a participant solve the same question twice to avoid answer memorization. Four volunteers are a convenience sample, **not statistical evidence**.

## Facilitation instructions

1. Use the **same seeded reference month (2026-10)** and unchanged source files for everyone.
2. Manual condition: allow normal CSV/Excel filtering, sorting, pivoting and arithmetic; do not allow assistant/chatbot help. For T06 apply the published teaching heuristic: **REVIEW iff total available < monthly completed units sold**.
3. RetailIQ condition: start the local app from the same seed with RETAILIQ_MODE=offline. Each question is entered independently with no prior conversation state. If using full mode instead, use a separate pilot and identify that changed condition; the original pilot specifically measures offline deterministic support.
4. Both conditions start with file/app already open. Timer starts **when the participant receives the question**, ends after they record the final answer and reasoning, **including reading and checking the evidence**.
5. Facilitator marks correct as 1 **only** if all listed required fields and the business decision agree with the separate answer key; otherwise 0. Do not count just receiving HTTP 200 as a correct decision. Record the participant's actual answer in answer_recorded, elapsed positive seconds in duration_seconds, optional manual_steps (count manual filters/lookups/calculations), and notable usability issues in notes.
6. Use pseudonymous P01–P04. Do not record names, API keys, customer information or confidential input. Copy each participant's rows into the master CSV without altering assignment columns. Do not expose the facilitator key to participants.

## Analysis

Once the CSV has actual observations, run:

~~~bash
python -m scripts.business_pilot_analyze --folder data/business_pilot_run1 --output data/business_pilot_run1/summary.json
~~~

**Blank:** NOT_MEASURED, no efficiency metric. **Partial:** INCOMPLETE, number of missing observations and **no** efficiency claim. **All 24 complete:** COMPLETE_EXPLORATORY, correctness rate and median time **for correct answers** by method; additional per-task descriptive summaries and an illustrative time difference only if both method medians exist.

The computed percentage, if any, describes **these four volunteers and this synthetic dataset**. It is not an estimate of financial savings, production agent quality, real user impact, causality or statistical significance. **Always report answer correctness alongside time; a faster wrong answer is not success.** Small samples and different task difficulty restrict conclusions.

## Report narrative (after observations exist)

- Context: internal synthetic inventory & sales decision-support pilot; source month 2026-10.
- Method: four volunteers, 24 counterbalanced task trials, manual CSV versus offline RetailIQ; fixed six prompts.
- Accuracy first: correct tasks out of 12 per method, plus any major incorrect decisions.
- Completion times: descriptive medians and per-task breakdowns of correct trials, with number of successful trials stated.
- Qualitative notes: which CSV steps were tedious, UI issues, missing freshness evidence and user feedback.
- Limits: no real retailer, no generalization, no business ROI, no controlled random sample.
- Next decision: retain narrow scope or address a high-impact usability issue before adding more agent functionality.

**Do not present any numerical “time saved,” “productivity gain,” or “business ROI” until the observation sheet is complete and verified.**

Related: [Selected Business Problem](21_INVENTORY_SALES_BUSINESS_SCOPE.md), [Golden Business Scenarios](22_BUSINESS_GOLDEN_SCENARIOS.md), [Technical E2E & Benchmark](20_LOCAL_E2E_BENCHMARK_EVIDENCE.md).

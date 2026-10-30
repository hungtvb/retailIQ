# Week 1 — Rubric, scope and acceptance

**Rubric source:** supplied evaluation image: **2 sections / 7 checkpoints**. The older four-checkpoint transcription is retained only [in archive](../../archive/2026-10-30/legacy/00_WEEK1_OFFICIAL_CHECKLIST.md). This document states requirements; [EVIDENCE](EVIDENCE.md) states execution outcomes.

## 1. Business Problem — 3 checkpoints

**Objective:** evaluate the team's understanding of the business problem and expected value.

| ID | Official checklist requirement | RetailIQ explanation |
|---|---|---|
| **BP-1** | Clearly identify the problem to be solved | Multi-screen filtering, SKU/period reconciliation and analysis across existing retail tools, **not** “the retailer has no tools” |
| **BP-2** | Understand target users and their pain points | Retail/store operators, managers and analysts; unnecessary navigation and interpretation overhead |
| **BP-3** | Explain expected value, benefits or business impact | **Faster · Easier · Reliable** information tasks; measurable hypotheses, not invented ROI |

**Canonical content:** [Business Problem and personas](../../PROJECT.md).

## 2. Solution Design + Demo + Testing — 4 checkpoints

**Objective:** evaluate the ability to design a solution and apply course knowledge.

| ID | Official checklist requirement | Evidence or explanation |
|---|---|---|
| **SD-1** | Present a clear workflow and solution architecture | User → FastAPI → LangGraph route → SQL / Product RAG → grounded answer; [architecture](../../ARCHITECTURE.md) |
| **SD-2** | Demonstrate Week 1 concepts | FDE; harness architecture layers/components; LangChain context/tools; Chain, Agent, multi-agent **Subagent, Handoff, Skill, Router, Custom Workflow**; LangSmith operations; Agent Cost & ROI |
| **SD-3** | Successfully demonstrate the solution | Stock, revenue, top sellers, product documentation and optional cross-source review |
| **SD-4** | Conduct testing and explain limitations, risks and improvements | Tests, real/fixture/mocked evidence, RAGAS, LangSmith, unsafe or unsupported questions |

**Teaching application:** [Week 1 DESIGN](DESIGN.md); **live demo:** [RUNBOOK](RUNBOOK.md); **actual results:** [EVIDENCE](EVIDENCE.md).

## Week 1 required implementation slice

- **Inventory and sales:** verified, read-only SQL queries with correct completed-order month, SKU, stock and revenue semantics.
- **Product RAG:** LangChain/Chroma embeddings and source citations for product knowledge.
- **LangGraph workflow:** route to appropriate specialist, use multi-agent patterns only when warranted by the question.
- **RAGAS and LangSmith:** evaluation scores and a real remote trace must be distinguishable from local simulated proof.
- **FDE / harness / cost:** show why the architecture solves the user task and calculate assumptions without claiming actual savings.

**Representative questions:** current stock by SKU and location; selected-month revenue; top five sellers by units; product capabilities and cited source. Cross-source top-seller vs stock is one illustration, never the entire project. Flexible follow-ups and arbitrary rankings remain quality targets and require separate verification.

## Scope guardrails and references

Week 1 is local, synthetic and read-only. No automatic orders/price changes or production integration. Weeks 2–4 original required capabilities—including the **five-agent Week 4 approved order scenario**—are maintained in the [course baseline](../../COURSE_PLAN.md). Original [course lesson references](../../archive/2026-10-30/legacy/00_WEEK1_LESSON_REFERENCES.md) and [PRD user stories](../../archive/2026-10-30/legacy/12_Product_Brief_and_PRD.md) are preserved.

**Acceptance rule:** every PASS must include execution mode, tested SHA, date, environment and reproducible artifact; an older run does not certify newer source code.

# Week 1 — Presentation & Demo Checklist

> **Source:** Checklist supplied by the team for the course's Week 1 review. Wording preserved in substance and grouped as four numbered checkpoints for readability. This is the **evaluation rubric**, distinct from the implementation-status matrix.
>
> **Project:** RetailIQ Copilot — Omnichannel Inventory Intelligence & Conversational Analytics.

## 1. Present a clear workflow and solution architecture

- Present the business use case and an understandable user-to-result workflow.
- Explain the components and how the application orchestrates model, context, tools and data.
- Show why the selected architectural design fits the retail problem.

## 2. Demonstrate the application of concepts learned in Week 1

All the following concepts were explicitly listed in the supplied checklist:

- **Introducing Forward Deployed Engineering (FDE)** — describe the domain-first, iterative approach. FDE is a **delivery approach**, not a software module that must be implemented.
- **Harness Architecture: layers and components** — map context, execution, tools and verification/operations to the actual solution.
- **Harness Context and Tools with LangChain**, including:
  - Chain
  - Agent
  - Multi-agent patterns: **subagent, handoff, skill, router, custom workflow**
- **Harness Operations with LangSmith** — demonstrate operational visibility/trace evidence, not merely the presence of configuration variables.
- **Agent Cost and ROI Estimation** — show assumptions, cost drivers and calculations; distinguish estimates from measured token usage or business savings.

> The checklist says **demonstrate application of concepts**. It does not explicitly state that every agent pattern must be deployed as a production multi-agent system in Week 1. The team elected to implement concrete RetailIQ examples for Router, Subagent, Handoff, Skill and Custom Workflow to make the explanation stronger.

## 3. Successfully demonstrate the solution

Demonstrate that the solution runs and answers the intended business questions. For RetailIQ, the project brief additionally specifies:

- Inventory lookup via SQL Tool.
- This-month revenue and top-seller analytics.
- Product information via Product RAG and VectorDB.
- LangGraph workflow and appropriate agent/tool routing.
- RAGAS evaluation and LangSmith execution evidence.

**Acceptance distinction:** An offline local fallback proves basic business logic/UI behavior, but **does not prove** live LangGraph, LLM, Chroma vector search, RAGAS or LangSmith integration.

## 4. Conduct testing and explain limitations, risks, or potential improvements

- Show test cases, observed outputs, pass/fail results, and any unavailable verification.
- Discuss risk of incorrect routing, wrong SQL/KPI interpretation, irrelevant RAG retrieval, hallucinations, data freshness and security/privacy.
- State the limits of synthetic data and local, unauthenticated demonstration.
- Identify technical and business improvements, including measurement of real latency/token costs and further evaluation.

## Suggested evidence map (implementation references, not claims of completion)

| Checklist | Live UI / demo | Source / document | Evidence gate |
|---|---|---|---|
| 1. Workflow & architecture | AI Assistant and live agent activity timeline; architecture slides | `docs/02_Architecture_and_Tech_Stack.md`, `retailiq/orchestration/week1_graph.py` | Explain real control/data flow |
| 2. FDE | AS-IS → TO-BE and scoped retail problem | `docs/07_FDE_Harness_and_Patterns.md` | Hypotheses clearly marked; no invented user interviews |
| 2. Harness / patterns | Router, specialist agents, supervisor/subagents, handoff and skills | `retailiq/orchestration/`, `retailiq/skills/`, `docs/10_FDE_MultiAgent_Session_Implementation.md` | Real code path; separate offline simulation from compiled graph |
| 2. LangSmith | Tracing project UI + correlated request evidence | `retailiq/core/config.py`, `retailiq/observability.py` | **Actual remote trace**, not just local JSONL logs |
| 2. Cost / ROI | Cost & ROI tab, scenario sensitivity | `retailiq/domain/economics.py`, `docs/08_Agent_Cost_ROI.md` | Transparent assumptions; real token costs only if measured |
| 3. Successful demo | Four retail questions, multi-turn agent routing, product sources | `/ask/stream`, SQL and Product RAG paths | Full AI mode with real embedding/model calls |
| 4. Testing / risks | Execution Logs, test report and limitations slide | `tests/`, `docs/09_Week1_Checklist_and_Evidence.md` | Repeatable results, honest gaps, RAGAS report |

## Pre-demo verification checklist

- [ ] Local seed, application startup and unit/API tests run on the actual demo machine.
- [ ] Full LangGraph execution completes the inventory and sales use cases with the configured LLM.
- [ ] Product RAG retrieves source-grounded vector contexts and answers a product question.
- [ ] A real RAGAS report is produced; scores and failed cases are shown transparently.
- [ ] A real LangSmith trace exists for at least one evaluated agent request.
- [ ] Live chat timeline shows Router → Agent → Tool (and Handoff/Subagent/Skill on applicable questions).
- [ ] ROI dashboard labels all assumed values; observed usage is distinguished from forecasts.
- [ ] Testing, current limitations, risks and next improvements are explained.

## Related documents

- [Project requirements across all four weeks](00_PROJECT_REQUIREMENTS.md)
- [Week 1 implementation/evidence matrix](09_Week1_Checklist_and_Evidence.md)

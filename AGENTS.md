# RetailIQ — Repository Working Contract

## Source of truth
The instructor's **Domain #15 Retail / E-commerce** four-week assignment is the acceptance contract; start from `docs/00_PROJECT_REQUIREMENTS.md` and `docs/14_Requirements_Traceability.md`. The four "weeks" are now **capability milestones, not delivery deadlines**. RetailIQ is an independently developed project with no former 60-minutes/day or four-week engineering timebox. The business objective remains **Faster, Easier, Reliable**.

## Four required milestones
1. **AI Assistant:** LangGraph, reviewed SQL tool use, Product RAG / vector database, RAGAS, LangSmith, demonstrable inventory/sales/product questions.
2. **Reliable Assistant:** Semantic definitions, freshness routing, actual Inventory/Order MCP tool calls, conversation/customer memory, hybrid search, reranking, query rewriting and evidence.
3. **Governed Copilot:** HITL interrupt/resume and manager approval, scoped access control, KPI alerts, token/cost optimization, Langfuse, DeepEval, security/governance evidence.
4. **Multi-Agent Retail OS:** Five specialist agents (Inventory Search, Fulfilment Optimisation, Customer Context, Dynamic Pricing, Order Management), A2A-style coordination, verification/retry loop, deep agent report, order workflow with approval. A named deterministic role does not by itself satisfy autonomous agent requirements.

## Mandatory implementation workflow
- **Requirement first.** Before changing a feature, name the *instructor requirement* and its relevant existing code, the architectural gap, and the minimum observable acceptance criteria. Record the result in the requirements/evidence traceability matrix.
- **System first, not query first.** For a failed question, determine whether the defect is in intent/plan, context, routing, tool/data, verification or response. Fix the shared contract when justified; do not endlessly add keyword-specific special cases.
- **Reuse existing components.** Prefer a coherent cross-domain fix over a new framework, separate service or speculative feature. Do not let repeated revenue-query improvements crowd out other required Retail capabilities.
- **Do not substitute simulations for live evidence.** Differentiate offline deterministic SQL, mocked tool, real MCP stdio, compiled LangGraph, real provider LLM/RAG, LangSmith/RAGAS, browser E2E, and any production behavior. Label the exact execution mode and commit for each PASS.
- **Safety and correctness.** Business facts must come from validated read-only data or cited documents. Never silently drop the requested entity, SKU, period, rank, channel, location or authorization scope; clarify unsupported constraints. Do not claim production RBAC, payment or purchase order effects for teaching simulations.
- **Finish the current slice before moving on.** Run targeted tests and the complete relevant CI/strict acceptance suite. Read failure logs, fix regressions, rerun, and only then report PASS. A green unit-test run without independent business acceptance is insufficient.
- **No unattended scope change.** Do not add agents, UI redesigns, infrastructure or unrelated business queries unless explicitly required or evidenced as a prerequisite. If prior work is red, fix it before opening a new feature.
- **Repository discipline.** Continue on the active feature branch unless directed otherwise. Do not merge into `main` without explicit approval. Never commit secrets, keys, private data or unverifiable evidence.

## Required status reporting
For each implemented slice state: (1) requirement covered, (2) files/commit, (3) tests/evidence with run link, (4) remaining gaps. Explicitly say **not verified** where evidence is absent. Update requirement coverage across all four milestones, not just the currently edited module.

## Current near-term engineering priorities
1. Return `feature/product-workspace-v1` to a green strict CI after the revenue-query changes.
2. Audit cross-domain NLU/planning/context/verification against the instructor's full scope, not merely revenue.
3. Work requirement-by-requirement through missing Week 1–4 capabilities, implementing real behavior and independent evidence.

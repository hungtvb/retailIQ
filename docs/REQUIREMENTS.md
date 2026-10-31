# RetailIQ — Product & Engineering Requirements

**Status:** requirements baseline, **not** a completion report. This consolidates the supplied AI Flezi Retail/E-commerce assignment and RetailIQ's business objectives. The course brief in the repository is a team summary, not a verbatim certified instructor transcript; confirm any disputed wording against the original handout.

This file describes **what must be supported**. The [roadmap](COURSE_PLAN.md) owns the original four-week teaching sequence. The [capability ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md) tracks implementation/evidence and may contain historical statuses.

## Business requirements

| ID | Requirement | Acceptance principle |
|---|---|---|
| BR-01 | Retail operations users can request inventory, sales and product information through natural language | Representative jobs return verifiable answers without requiring database knowledge |
| BR-02 | Multi-source decisions preserve correct identity and scope across steps | Same SKU, reporting period, location, status and other requested constraints are retained |
| BR-03 | Answers disclose the underlying facts or documents and important limitations | Unsupported claims are clarified, qualified or declined instead of fabricated |
| BR-04 | Evaluate Faster, Easier and Reliable against equivalent manual tasks | Report comparable end-to-end time, effort and answer correctness; do not claim benefits before measurement |

## Functional capabilities

| ID | Requirement | Minimum observable acceptance |
|---|---|---|
| CAP-01 | Natural-language inventory/sales analytics backed by reviewed SQL, using LangGraph and LangChain tools | Correct stock, revenue and top-seller queries; routing/tool execution is observable |
| CAP-02 | Product RAG using LangChain, document ingestion, embeddings and a vector database | Product details are retrieved from source documents; responses identify supporting sources |
| CAP-03 | Agent patterns where justified: routing, specialists/subagents, handoff, skills and custom workflow | Execution evidence distinguishes real calls/control transfer from deterministic routing or UI decoration |
| CAP-04 | Conversational context and follow-up handling | Product/rank/period/location references remain consistent and isolated between sessions |
| CAP-05 | RAGAS quality evaluation and LangSmith tracing | Actual evaluation output and trace IDs exist for the relevant model, dataset and commit |
| CAP-06 | Freshness-aware source selection: live, 15-minute, hourly and daily tiers | Selected source meets or explicitly fails requested freshness; target tier alone never proves freshness |
| CAP-07 | Governed semantic definitions for stock, revenue, top sellers and order state | Shared definitions and source-of-truth contracts are consistently applied |
| CAP-08 | MCP Inventory and Order APIs/resources with LangChain MCP integration | Real tool transport/response contract verified, distinct from direct SQL and mock adapters |
| CAP-09 | Conversation/customer-context memory with short-term and long-term strategy | Scoped recall, consent, isolation and removal are demonstrable; no fake authenticated identity |
| CAP-10 | Advanced retrieval: hybrid search, reranking and query rewriting | Reproducible retrieval-quality comparison and per-source reliability/accuracy report |
| CAP-11 | Human-in-the-loop approvals and governed row-level access | Sensitive actions pause for an authorized reviewer; denied, resumed and unauthenticated paths are tested |
| CAP-12 | KPI alerts plus measured token and operational cost controls | Threshold, authorization, delivery/failure handling and real cost/usage evidence |
| CAP-13 | Langfuse observability, DeepEval regression and security/PromptOps/governance reporting | Captured tool/model traces, repeatable evaluation and reviewable security findings |
| CAP-14 | Five required specialist agents: Inventory Search, Fulfilment Optimisation, Customer Context, Dynamic Pricing and Order Management | Each required agent has a distinct responsibility, actual behavior and tested interface |
| CAP-15 | A2A-style coordination, verification/retry, deep decision report and manager-approved order workflow | Actual agent control/evidence transfer, negative cases and explicit approval before sensitive finalization |

Course-required technologies and five specialist roles remain required even where the local implementation presently provides only simulations. Do not remove them to simplify documentation or replace a real capability with a renamed function.

## Quality, safety and evidence requirements

| ID | Requirement |
|---|---|
| QUAL-01 | Financial amounts, inventory and rankings use reviewed business definitions and authoritative structured data; never run unrestricted LLM-generated SQL |
| QUAL-02 | Reject or clarify unsupported/ambiguous entity, period, location, authorization or freshness constraints; never silently broaden the scope |
| QUAL-03 | Separate **offline deterministic**, **mocked**, **real local MCP**, **provider-backed LLM/RAG**, and **production** claims and tests |
| QUAL-04 | Verify business scenarios with independent oracles and relevant negative cases; a unit test, graph image or green CI is not sufficient business acceptance |
| QUAL-05 | Record test mode, commit, version/configuration, measured result and reproducible run/evidence location; generated execution evidence is stored **outside Git** |
| QUAL-06 | Protect credentials and private data. No sensitive business mutation without an authenticated and authorized approval mechanism |
| QUAL-07 | Support reproducible local development using synthetic data. Local tests never establish production security, data freshness or realized ROI |

## Acceptance and traceability

Representative acceptance must cover **single-source** queries, **multi-source** joins, **conversational follow-ups**, **data errors**, **retrieval grounding**, **source freshness**, **MCP transport**, **approval/access controls** and **multi-agent execution**. Check exact expected results and negative cases, not just whether an API returned success.

- [Business questions and intended outcomes](PROJECT.md)
- [Detailed behavioral scenarios](27_BEHAVIORAL_ACCEPTANCE_MATRIX.md)
- [Implementation and evidence status (historical ledger)](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md)
- [Trusted KPI, data and API contracts](DATA_API.md)
- [Original course milestones and planning sequence](COURSE_PLAN.md)

**Requirement ≠ implementation ≠ evidence.** A completed local scenario is not a certificate of live provider behavior, real external retailer integration, secure workflow authority or user productivity improvement.

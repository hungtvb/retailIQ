# RetailIQ — Week 1 Compliance Audit against the Supplied Course Sources

**Audit date:** 2026-10-28  
**Scope:** `hungtvb/retailIQ`, `main`; source inspection and offline regression.  
**Primary reading list:** [00_WEEK1_LESSON_REFERENCES.md](00_WEEK1_LESSON_REFERENCES.md)  
**Rubric:** [00_WEEK1_OFFICIAL_CHECKLIST.md](00_WEEK1_OFFICIAL_CHECKLIST.md)  
**Testing performed:** `python -m pytest -q --disable-warnings --maxfail=1` in the latest local source tree: **74 passed, 1 skipped**. This tests offline logic, HTTP/SSE and mocks, **not** actual external LLM, LangSmith, RAGAS or Chroma E2E.

## Judgment vocabulary

- **Aligned:** Implementation uses the documented mechanism and there is inspectable code/test evidence. This does not certify provider integration.
- **Partial:** Related code exists but important semantics, real usage or evidence are missing.
- **Not verified:** Configuration or script exists but has not produced the required real external evidence.
- **Not implemented:** No suitable code path identified in reviewed source.

## Lesson 02 — Agent harness fundamentals

| Reading/topic | RetailIQ evidence | Judgment | Required follow-up |
|---|---|---|---|
| Agent Harness Architecture | `orchestration/week1_graph.py`, `observability.py`, `api/http.py` | **Partial** | Present exact five layers: **Orchestration, Context Management, Tool Integration, Verification, Operations**. UI/Experience is outside the harness core, not a substitute layer. Add verification gate, execution budget and cost guardrails proportionally. |
| Context Engineering | `infrastructure/sessions.py` saves chat history; `resolve_followup()` restores product context; Product RAG adds source context | **Partial** | Clarify model/tool/lifecycle context, history/record selection, truncation/token budgets, trusted vs. untrusted sources. Current 12-message history cap is not a token budget. |
| Tools | `agents.py::build_sql_subagents` uses `@tool`; `domain/analytics.py` uses vetted read-only SQL | **Partial** | Tool schemas are defined, but supervisor tool invocations are fixed in Python rather than chosen by a model-driven agent. Add typed tool output/error contracts, explicit scope and dynamic tool demo only where valuable. |
| LangSmith Observability Concepts | Structured local JSONL, SSE timeline, LangSmith environment support | **Partial / live not verified** | Distinguish **run**, **trace**, **thread**, and trajectory; correlate `request_id` and session with a real LangSmith run/trace. Local events are not a remote nested trace. |

Course source: https://harness-engineering.ai/blog/agent-harness-architecture-how-the-system-works-under-the-hood/ and relevant LangChain/LangSmith links in the index.

## Lesson 03 — Agents, patterns and streaming

| Reading/topic | RetailIQ evidence | Judgment | Required follow-up |
|---|---|---|---|
| LangChain Agents | `retailiq/orchestration/agents.py`: fixed SQL functions and LangGraph subgraphs | **Partial** | `create_agent`-style model→tool→model loop absent for Sales/Inventory/Supervisor. Say **routed specialist workflow**, not that all nodes are autonomous LangChain agents. If demonstrating full agent architecture, implement one scoped model-driven supervisor with tool delegation. |
| LangChain Tools | Reviewed SQL wrappers via `@tool`, `tool.invoke` | **Aligned for tool definitions; partial for model-controlled invocation** | Give scoped tool descriptions, validated arguments/results and tests for tool failure. |
| Structured Output | `week1_graph.py::route`: Pydantic `Route`, `with_structured_output` | **Aligned in source / live not verified** | Verify model supports structured output, log and evaluate fallback accuracy; differentiate model `with_structured_output` from `create_agent(response_format=...)`. |
| Multi-Agent Overview | Router, Product/Sales/Inventory nodes and Supervisor | **Partial** | Roles are separated, but fixed delegation and hard-coded reviews lack adaptive task decomposition. Multi-agent is optional in simple cases; justify overhead. |
| Subagents | `build_sql_subagents()` compiles isolated graphs; Supervisor invokes both sequentially | **Partial** | Docs describe **main agent decides which subagents to invoke and combines outputs**. Current `replenish_review()` always invokes both in fixed order. Preserve narrow context, add decision if claiming supervisor-style subagents. |
| Handoffs | Sales node returns `Command(update=...,goto='inventory_agent')`; SQLite stores `active_agent` between turns | **Aligned for graph-level transfer; partial for lesson's tool-driven handoff** | Source's persistent `active_agent` is useful; no LangGraph checkpointer for full state. Course example is *handoff tool* updating state; if a model calls one, return matching ToolMessage. Direct graph node Command does **not** require ToolMessage. |
| Skills | Allowlisted `retailiq/skills/*.md` and `load_skill()`; Product Agent inserts skill into prompt | **Partial** | Product skill affects behavior; Sales/Inventory/Supervisor load skill but discard returned content. Make selected skill actually affect agent instructions/tool choice, or label read-only rules as documented business policies rather than agent skills. Progressive disclosure is the target. |
| Router | `AGENT_FOR_INTENT`, Pydantic classifier, `Command(goto=...)` | **Aligned for single-agent routing** | Docs also describe parallel `Send` and synthesis for multi-source questions; not required for existing single-path intents. Document rule-first fallback vs LLM classification honestly. |
| Custom Workflow | `StateGraph`, typed `State`, specialized nodes, `Command` | **Aligned in code** | Add compiled LangGraph live test; current environment's graph smoke test skipped. |
| Streaming | `POST /ask/stream`: actual backend log events → request-local queue → SSE | **Aligned for custom application events; partial vs native LangChain streaming** | Frontend sees real agent events, but `graph.invoke` yields final result; no `graph.stream`/`astream` node updates or LLM token streaming. Distinguish these mechanisms in demo. |

Official pattern sources:
- https://docs.langchain.com/oss/python/langchain/agents
- https://docs.langchain.com/oss/python/langchain/multi-agent/subagents
- https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs
- https://docs.langchain.com/oss/python/langchain/multi-agent/skills
- https://docs.langchain.com/oss/python/langchain/multi-agent/router
- https://docs.langchain.com/oss/python/langchain/multi-agent/custom-workflow
- https://docs.langchain.com/oss/python/langchain/streaming

## Lesson 04 — LangSmith observability and evaluations

| Reading/topic | RetailIQ evidence | Judgment | Required follow-up |
|---|---|---|---|
| Observability Concepts | Local `request_id`, `session_id`, event logs and UI | **Partial** | LangSmith run/trace/thread distinction, nested spans and trajectory still need real evidence. |
| Trace LangChain Applications | `core/config.py::configure_langsmith`, graph `run_name` and tags | **Not verified** | Configure LangSmith project/key, produce live trace, associate safe `request_id`/`session_id` metadata; verify submission and link. Remember LangSmith may capture prompts/responses, unlike the redacted local logger. |
| Manage Datasets | `data/demo_cases.json` and RAGAS script test questions | **Partial** | No verified LangSmith dataset or dataset version created. Create a compact golden set: 4 baseline questions plus no-match, ambiguous, handoff, hallucination and prompt-injection cases; use reference answers and versioning. |
| Evaluation Concepts | `tests/` deterministic unit/API tests; `scripts/eval_ragas.py` for faithfulness/relevancy | **Partial** | Unit tests are not output-quality evaluations. Run offline evaluation experiments against dataset; capture actual RAGAS and/or LangSmith evaluator results; report false routes and failed queries. |
| Cost Tracking | `agents.py` captures Product-Agent `usage_metadata` when available | **Partial / provider rates unverified** | Include Router LLM, Product LLM, embeddings, retries, judge calls and custom tool costs; configure actual model/deployment pricing where LangSmith cannot auto-map a custom gateway. |

Sources: https://docs.langchain.com/langsmith/observability-concepts, https://docs.langchain.com/langsmith/trace-with-langchain, https://docs.langchain.com/langsmith/manage-datasets, https://docs.langchain.com/langsmith/evaluation-concepts, https://docs.langchain.com/langsmith/cost-tracking.

## Lesson 05 — Cost and ROI economics

| Reading/topic | RetailIQ evidence | Judgment | Required follow-up |
|---|---|---|---|
| LangSmith Cost Tracking | `domain/economics.py`, UI dashboard; partial model usage logs | **Partial** | Forecasted request tokens/prices are not actual traced cost. Capture provider/model usage and appropriate rates; aggregate per trace and session. |
| Cost Optimization | Simple rule-first routing and SQL read-only path avoid some LLM expense | **Partial** | Measure calls, latency, retries, context size and model usage; compare cheaper routing/caching approaches **without reducing answer quality**. |
| AI Agent ROI Calculator | `domain/economics.py` computes gross savings, net savings, payback and scenarios | **Aligned as an illustrative financial model** | Clearly mark hypothetical workload, human-time savings, hourly rate, implementation and monthly operating costs. For production ROI, measure manual baseline + actual successful automation and ongoing costs. |
| Agentic AI Cost Governance | ROI dashboard; no policy enforcement | **Not implemented as governance** | Request/session/token budget, retry/step limits, cost alerts or stop conditions. Week 1 can describe these limits; Week 3 can implement comprehensive operational controls. |

Sources: https://docs.langchain.com/langsmith/cost-tracking, https://harness-engineering.ai/blog/how-to-optimize-ai-agent-costs-without-sacrificing-performance/, https://harness-engineering.ai/blog/ai-agent-roi-calculator-measuring-the-business-value-of-agent-systems/, https://www.finout.io/blog/agentic-ai-cost-governance-controlling-spend-before-it-controls-you.

## High-priority engineering observations

1. **P0 — Full mode acceptance:** No confirmed live LLM → compiled LangGraph → SQL/Chroma Product RAG → RAGAS → LangSmith trace end-to-end evidence. Do not label PASS from deterministic offline tests.
2. **P0 — Observability:** `/ask/stream` emits real application events, but no verified LangSmith trace/thread/run link; correlating IDs should be explicit.
3. **P1 — Correct the harness diagram:** `docs/07_FDE_Harness_and_Patterns.md` previously showed Experience as the first of five layers; fix to the source's five layers and show UI outside the harness.
4. **P1 — Agent/Subagent semantics:** Fixed delegation and SQL graphs are valid custom workflows; if claiming *model-directed* supervisor/subagents, add a bounded tool-calling loop with tests.
5. **P1 — Skill semantics:** Make loaded instructions operational; avoid merely reading a Markdown file to emit a success event.
6. **P1 — Context management:** 12 chat messages is a length cap, not a token budget; distinguish runtime state vs model context; checkpointer would improve graph persistence/restart recovery but is not the only valid way to store chat history.
7. **P1 — Verification:** Add response-grounding and retrieval relevance checks plus negative tests and reference-based evaluation set.
8. **P1 — Cost accounting:** Per-request measured usage, custom Azure/gateway pricing, and clear separation from illustrative business ROI.

## Demo evidence order

1. Present business AS-IS → TO-BE and the corrected 5-layer harness architecture.
2. Show stock/revenue/top sellers with true SQL evidence and a compiled LangGraph request.
3. Show Product RAG with retrieved source metadata.
4. Show a session follow-up and **graph-level** Sales→Inventory handoff.
5. Show a cross-domain replenishment review and describe fixed vs model-directed delegation truthfully.
6. Show real-time SSE application events **and** a separate real LangSmith nested trace.
7. Show dataset/evaluation outputs: test pass report, RAGAS quality metrics and failures.
8. Show token/cost evidence and clearly marked ROI scenarios.
9. State security, freshness, synthetic-data and performance limitations.

## Audit limits

Source review is not a substitute for a live provider run. External services and paid model credentials were not used for this audit. The independent harness/ROI/FinOps blog posts are supplementary references; their architecture recommendations should not be mistaken for LangChain API contracts or the literal course rubric. No claim of production-ready agent governance is made.

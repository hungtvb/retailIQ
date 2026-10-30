# RetailIQ — Instructor Capability Acceptance Ledger

**Baseline:** Domain #15 Retail / E-commerce instructor brief as captured in
[00_PROJECT_REQUIREMENTS.md](00_PROJECT_REQUIREMENTS.md).
**Development mode:** independent; the four "weeks" are milestones, not deadlines.
**Branch:** `feature/product-workspace-v1`.
**Status date:** 2026-10-30.

This is the *active* engineering gate. Status must be supported by code **and**
reproducible execution. A green CI run establishes only its explicit scenarios,
not full provider quality or the entire course requirement.

## Evidence status legend

- **LOCAL PASS:** deterministic SQL, local stdio MCP, browser or controlled fixtures passed; read the specific gate.
- **MOCKED PASS:** compiled graph/fake model or fake vector provider; not an actual provider trace.
- **IMPLEMENTED / LIVE PENDING:** code exists but a real model/external service or quality report is still needed.
- **PARTIAL:** part of the required capability exists, remaining requirement remains open.
- **OPEN:** no sufficient implementation/evidence identified.

## Instructor requirements and evidence

| ID | Instructor requirement | Implementation | Evidence / status | Acceptance still required |
|---|---|---|---|---|
| W1-01 | LangGraph router, SQL Inventory/Sales | `retailiq/orchestration/week1_graph.py`, `retailiq/domain/analytics.py` | LOCAL + MOCKED PASS: compiled graph tests and SQL acceptance | Current-commit real LLM execution and request trace |
| W1-02 | Product RAG, LangChain, vector database | `retailiq/rag/indexing.py`, `retrieval.py`, `orchestration/agents.py` | LOCAL parser/index-contract tests; IMPLEMENTED / LIVE PENDING | Indexed Chroma query with actual embeddings, source grounded answer |
| W1-03 | RAGAS | `scripts/eval_ragas.py` | IMPLEMENTED / LIVE PENDING | Current-commit metric report and failed cases |
| W1-04 | LangSmith | `retailiq/core/config.py`, graph tracing | IMPLEMENTED / LIVE PENDING | Current-commit remote trace with correlated request ID |
| W2-01 | Freshness-aware routing: live/15-min/hourly/daily | `retailiq/domain/semantic.py`, `domain/workflow_demo.py` | PARTIAL: freshness timestamps and local scenarios | Query-to-source choice plus per-source reliability/freshness report |
| W2-02 | Governed semantic metrics | `retailiq/domain/semantic.py` | LOCAL PASS: metric definition and freshness contracts | Include order-state contract and verify use in all workflow paths |
| W2-03 | MCP Inventory and Order APIs + LangChain adapter | `retailiq/mcp_server.py`, `mcp_adapter.py` | LOCAL PASS: real stdio subprocess + browser-backed MCP calls | Evidence is local stdio, not a hosted MCP or enterprise API |
| W2-04 | Customer context memory (short & long term strategy) | SQLite sessions / bounded history / LangGraph checkpoint | PARTIAL: short-term context isolation tested | Explicit consent/scope, persistent customer context policy and tests |
| W2-05 | Hybrid retrieval, reranking, query rewriting | `retailiq/rag/advanced_retrieval.py`, `retrieval.py`, `scripts/eval_retrieval.py` | LOCAL/MOCKED: index-backed lexical + fake-vector test; deterministic term expansion; metric harness implemented | Provider-backed embedding retrieval evaluation against held-out queries; prove retrieval quality (Recall@k/MRR or equivalent), not just code presence |
| W2-06 | Source reliability and accuracy report | Existing 20+/19/14 synthetic suites | PARTIAL: synthetic SQL/MCP reliability evidence | Consolidated per-source breakdown, freshness results and retrieval quality |
| W3-01 | HITL approval | `retailiq/domain/workflow_demo.py` | PARTIAL: simulation of gate with persisted local review | LangGraph interrupt/resume, authorized reviewer boundary, negative tests |
| W3-02 | Row-level security | Role-sensitive simulated location scope | PARTIAL: not authenticated RBAC | Authenticated principal and enforced read scope + isolation tests |
| W3-03 | KPI alerts | Workflow screening | LOCAL PASS for threshold fixtures; PARTIAL overall | Audited alert policy, authorized destination and failure behavior |
| W3-04 | Token optimisation, cost tracking | `retailiq/domain/economics.py`, usage events | PARTIAL: illustrative cost model | Measured real token/call/latency data, optimization baseline |
| W3-05 | Langfuse | None verified for current branch | OPEN | Actual trace ID and tool/span evidence |
| W3-06 | DeepEval | No confirmed live regression job | OPEN | Repeatable evaluation report with fixed model/data versions |
| W3-07 | Security review + PromptOps + governance reports | Runbooks, validation and security mitigations | PARTIAL | Reviewed threat model, prompt version tracking and governance report |
| W4-01 | Inventory Search specialist agent | Week 4 deterministic role | PARTIAL: role simulation only | Independent agent capability and tool/communication contract |
| W4-02 | Fulfilment Optimisation specialist agent | Week 4 deterministic role | PARTIAL | Independent agent workflow and allocation verification |
| W4-03 | Customer Context specialist agent | Week 4 deterministic role | PARTIAL | Bounded customer memory and protected context |
| W4-04 | Dynamic Pricing specialist agent | Week 3/4 pricing proposal role | PARTIAL | Governed agent proposal with evidence and real pause for approval |
| W4-05 | Order Management specialist agent | Week 4 draft + simulated gate | PARTIAL | Validated order workflow and human-controlled finalisation |
| W4-06 | A2A-style multi-agent orchestration | Local directed handoff events | PARTIAL | Agent-to-agent typed contracts and actual orchestrated invocations (not a displayed role chain) |
| W4-07 | Verification/retry loop + deep report | Stock/price checks, simulated replan, report | PARTIAL | Agent execution evidence with negative/retry cases and verified final justification |
| W4-08 | End-to-end order scenario with manager approval | Local read-only draft workflow | LOCAL PASS simulation; overall PARTIAL | Real graph approval/resume & secure actor check; no unauthorized order/price mutation |

## Active acceptance protocol

1. Select **one instructor requirement ID** as the engineering task. Define intended behavior and failure cases *before* coding.
2. Integrate with the current components; never create additional agent systems or unrelated business-query features merely to appear complete.
3. Test independently: correctness oracle, control/edge truth, side effects, malformed input and relevant browser/tool runtime.
4. Record exact **commit, execution mode, command, counts, artifact/run URL and remaining gaps**. If a provider is not configured, label it LIVE PENDING and do not substitute a fake model.
5. Keep CI green, then select the next requirement using dependencies: W2 memory/reliability → W3 authenticated governance/HITL/evaluation → W4 real specialist orchestration.

## Week 2 Advanced Retrieval local verification

- Default full-mode retrieval: `RETAILIQ_RAG_RETRIEVAL=hybrid`.
- Comparison path: `RETAILIQ_RAG_RETRIEVAL=vector`.
- Rewriting: explicit **deterministic multilingual term expansion**; *not* an LLM rewrite.
- Hybrid: original source manifest-verified Chroma candidates plus manifest-verified lexical candidates. Ranking uses reciprocal rank fusion and token overlap.
- Safety: changed/deleted/unindexed documents, recovery journal, vector timeout and injected source are covered by tests. Never claim these as provider quality metrics.
- Reproduction: `python -m pytest -q tests/test_advanced_retrieval.py tests/test_rag_module_hardening.py`; project CI also runs strict behavioral gates.
- Provider acceptance (still open): index actual product docs, then run `python -m scripts.eval_retrieval --confirm-live --out data/retrieval_eval_report.json` with actual embedding credentials. The script measures source Recall@3, MRR, per-source accuracy and mean retrieval latency for vector-only versus hybrid. It **must not** be marked PASS until the JSON report is produced and reviewed. Run `scripts/eval_ragas.py` separately for grounded answer faithfulness; retrieval accuracy is not a substitute.

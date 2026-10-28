# Week 1 — FDE, Harness Architecture and Agent Patterns

## 1. Forward Deployed Engineering (FDE) in RetailIQ
FDE is an iterative delivery approach: work closely with domain users to identify a concrete workflow, integrate with the actual data context, build a small usable solution, evaluate it and refine it from feedback. For this course's **synthetic** mock retailer, we simulate the discovery steps; **we have not interviewed actual store managers**, nor do we claim validated business savings.

**RetailIQ application:** Retail/E-commerce (#15) → Electronics & Accessories → inventory/sales reporting bottleneck hypothesis → data contracts (available stock, net revenue, top sellers) → four demonstrable questions → test/evaluation → feedback and Week 2 backlog.

**AS-IS:** users switch between inventory, sales and product documents and aggregate answers manually. **TO-BE (Week 1):** a local UI routes questions to a vetted SQL analytics function or Product RAG and shows sourced results. Explicit non-goals: execute orders, change prices or access production data.

## 2. Harness architecture — five layers from the Week 1 reading

The assigned [Agent Harness Architecture](https://harness-engineering.ai/blog/agent-harness-architecture-how-the-system-works-under-the-hood/) article names exactly **Orchestration, Context Management, Tool Integration, Verification, Operations**. RetailIQ's **web Experience/UI** sits *outside* these five harness layers.

| Harness layer | Responsibility | Actual RetailIQ implementation and current limit |
|---|---|---|
| **1. Orchestration** | Route, invoke specialists and control termination | `orchestration/week1_graph.py` uses LangGraph `StateGraph`, `Command` and specialist nodes. Not all specialists are autonomous tool-loop agents. |
| **2. Context Management** | Select model context, session state and trusted domain knowledge | `State` in `week1_graph.py`; 12-message bounded history in `api/http.py`; product RAG with metadata; business definitions. Missing measured context-token budget and native graph checkpointer. |
| **3. Tool Integration** | Validate, execute and normalize tool operations | `domain/analytics.py` exposes vetted read-only SQL via `agents.py` wrappers; Chroma Product RAG. Some calls are deterministic, not LLM-selected. |
| **4. Verification** | Check outputs and tool/answer quality | Parameterized business queries, `tests/`, `scripts/eval_ragas.py` and sourced product answers. LLM/Chroma E2E, RAGAS scores and relevance thresholds still pending. |
| **5. Operations** | Monitor execution, handle failures and control cost | `observability.py`, `api/logs.py`, SSE streaming, LangSmith configuration and ROI calculator. Live LangSmith traces and real per-request cost telemetry still pending. |

**Outside the harness:** `web/index.html`, `web/assets/` and FastAPI endpoints provide the application-facing Experience layer. These are important components, but not one of the article's five core harness layers.

**Control boundaries:** SQL must remain read-only and parameterized; untrusted product documents are data, not instructions; answers should cite product sources and never invent stock. Do not infer deployed authentication from these local controls.

**Lesson-source audit:** [00_WEEK1_LESSON_REFERENCES.md](00_WEEK1_LESSON_REFERENCES.md), [13_WEEK1_LESSON_COMPLIANCE_AUDIT.md](13_WEEK1_LESSON_COMPLIANCE_AUDIT.md).

## 3. LangChain / LangGraph concepts and architectural choice

| Concept/pattern | Week 1 evidence | Why / timing |
|---|---|---|
| Chain | Retrieval → context → LLM answer is a sequential chain concept; no separate `RunnableSequence` object implemented | Explain how it differs from an agent selecting tools dynamically |
| Agent/tool usage | LangChain `@tool` wraps SQL lookup; LLM classifies the intent, then graph dispatches | This is a **tool-using routed workflow**, not a general autonomous tool-selection loop |
| Router | **Implemented in source**: route `stock/revenue/top/product` | Predictable routing to authoritative data source |
| Custom workflow | **Implemented in source**: LangGraph `StateGraph` + conditional edges | Hybrid deterministic business calculations + generative product answer |
| Subagent | **Implemented in W1 FDE extension**: Supervisor delegates to scoped Sales/Inventory LangGraph subgraphs via LangChain tools | Week 4 expands to all mandated specialist agents |
| Handoff | **Implemented in W1 FDE extension**: Sales Agent → Inventory Agent via LangGraph `Command(goto=...)` | Week 4 extends inter-agent transfers |
| Skill | **Implemented in W1 FDE extension**: allowlisted, on-demand role policy instructions in `retailiq/skills/` | Skills differ from product RAG documents |
| Multi-agent | **Implemented as a focused read-only W1 scenario**: Retail Supervisor and three specialists | Week 4 still requires five mandated autonomous retail agents |

**FDE-driven choice:** Week 1 still routes simple questions to single specialists; a cross-domain question about bestselling items and available stock now invokes a Retail Supervisor with Sales and Inventory subagents. A follow-up can trigger an actual Sales→Inventory handoff. This makes each pattern demonstrable without implementing Week 4 write-side order/price operations. Details: `docs/10_FDE_MultiAgent_Session_Implementation.md`.

**Chat sessions:** the UI and `/api/sessions` persist local conversations in a separate SQLite DB and pass bounded recent history/active agent into the graph. This is application-level persistence, not a LangGraph checkpointer. No production identity or tenant protection is implied.

## 4. Structured local logging and LangSmith operations
Local application logging is now implemented in `retailiq/observability.py`: JSONL events, rotating files, per-request IDs, session context, agent and tool durations, safe exception stack frame *locations*, and a read-only loopback-only **Execution Logs** UI. See `docs/11_Logging_Observability.md`. This shows harness operations for the local demo but does **not** replace LangSmith execution traces.

### LangSmith remote traces
When `LANGSMITH_TRACING=true` with a valid separate `LANGSMITH_API_KEY`, show a trace containing the graph root run, routing, the executed tool path and LLM calls. Capture execution ID, latency and token usage where available, plus the timestamp and project. Use run metadata and compare 4 sample questions. **No live LangSmith trace is available in this environment.** Offline mode does NOT create a LangGraph trace.

## 5. Risk and limitations
Synthetic data are a repeatable test fixture, not representative operational data. Stock and sales snapshots are fixed, so answer freshness does not reflect production inventory. LLM routing may misclassify ambiguous queries; product RAG may retrieve irrelevant text or hallucinate. There is no user authentication, tenant segregation, role-based access, query cost enforcement or production-grade controls in Week 1. The local session API must not be exposed publicly. RAGAS/LangSmith cannot be marked PASS until real runs are captured.

## 6. How to speak about cost/ROI
Use `scripts/cost_roi.py` and `docs/08_Agent_Cost_ROI.md`. Do not call the scenario's fictional labor rates measured savings, or use sample dollar-per-token rates as a vendor quote. Time-to-payback only exists when verified monthly net benefit is positive.

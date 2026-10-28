# Week 1 — FDE, Harness Architecture and Agent Patterns

## 1. Forward Deployed Engineering (FDE) in RetailIQ
FDE is an iterative delivery approach: work closely with domain users to identify a concrete workflow, integrate with the actual data context, build a small usable solution, evaluate it and refine it from feedback. For this course's **synthetic** mock retailer, we simulate the discovery steps; **we have not interviewed actual store managers**, nor do we claim validated business savings.

**RetailIQ application:** Retail/E-commerce (#15) → Electronics & Accessories → inventory/sales reporting bottleneck hypothesis → data contracts (available stock, net revenue, top sellers) → four demonstrable questions → test/evaluation → feedback and Week 2 backlog.

**AS-IS:** users switch between inventory, sales and product documents and aggregate answers manually. **TO-BE (Week 1):** a local UI routes questions to a vetted SQL analytics function or Product RAG and shows sourced results. Explicit non-goals: execute orders, change prices or access production data.

## 2. Harness architecture — course-aligned interpretation
Different sources define "harness" differently. We use a **clear mapping** to this team's code rather than claiming one universal set of layer names.

| Layer | Responsibility | Actual RetailIQ implementation |
|---|---|---|
| Experience | User request/response | `web/index.html` + `retailiq/api/http.py` (FastAPI) |
| Context | Question, typed state, relevant documents and trusted data | `State` in `orchestration/week1_graph.py`; RAG chunks with source metadata; KPI definitions |
| Execution / Orchestration | Decision and control flow | LangGraph `StateGraph`, router + conditional edges |
| Tools & Data | Domain access and business operations | Vetted read-only SQL analytics over SQLite; product retrieval via Chroma |
| Verification / Operations | Evidence, testing, diagnostics, cost controls | pytest; planned/live RAGAS; LangSmith tracing when key is enabled; token/ROI model |

**Control boundaries:** SQL must remain read-only and parameterized; untrusted product documents are data not instructions; answer should cite product sources and never invent stock. Do not infer deployed authentication from these local controls.

## 3. LangChain / LangGraph concepts and architectural choice

| Concept/pattern | Week 1 evidence | Why / timing |
|---|---|---|
| Chain | Retrieval → context → LLM answer is a sequential chain concept; no separate `RunnableSequence` object implemented | Explain how it differs from an agent selecting tools dynamically |
| Agent/tool usage | LangChain `@tool` wraps SQL lookup; LLM classifies the intent, then graph dispatches | This is a **tool-using routed workflow**, not a general autonomous tool-selection loop |
| Router | **Implemented in source**: route `stock/revenue/top/product` | Predictable routing to authoritative data source |
| Custom workflow | **Implemented in source**: LangGraph `StateGraph` + conditional edges | Hybrid deterministic business calculations + generative product answer |
| Subagent | **Not implemented in W1** | Week 4 will introduce domain-specialist agents |
| Handoff | **Not implemented in W1** | Week 4 agent-to-agent coordination, with defined transfer control |
| Skill | **Not implemented as an agent skill** | Knowledge documents are not the same as on-demand executable skills |
| Multi-agent | **Not implemented in W1** | Five mandated agents are a Week 4 deliverable, not required to be faked in W1 |

**Why not multi-agent now?** Week 1 questions partition into two data sources and only require one router; adding a supervisor or handoffs would add calls, cost and failure points without clear user value. This illustrates selection among learned patterns. See LangChain multi-agent pattern documentation for the same distinctions.

## 4. LangSmith operations
When `LANGSMITH_TRACING=true` with a valid separate `LANGSMITH_API_KEY`, show a trace containing the graph root run, routing, the executed tool path and LLM calls. Capture execution ID, latency and token usage where available, plus the timestamp and project. Use run metadata and compare 4 sample questions. **No live LangSmith trace is available in this environment.** Offline mode does NOT create a LangGraph trace.

## 5. Risk and limitations
Synthetic data are a repeatable test fixture, not representative operational data. Stock and sales snapshots are fixed, so answer freshness does not reflect production inventory. LLM routing may misclassify ambiguous queries; product RAG may retrieve irrelevant text or hallucinate. There is no user authentication, role-based access, query cost enforcement or production-grade controls in Week 1. RAGAS/LangSmith cannot be marked PASS until real runs are captured.

## 6. How to speak about cost/ROI
Use `scripts/cost_roi.py` and `docs/08_Agent_Cost_ROI.md`. Do not call the scenario's fictional labor rates measured savings, or use sample dollar-per-token rates as a vendor quote. Time-to-payback only exists when verified monthly net benefit is positive.

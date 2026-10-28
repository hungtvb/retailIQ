# Architecture & Tech Stack

**Business goal:** Reduce user interaction complexity and, where supported by measurement, end-to-end task completion time for retail information access, **without sacrificing correctness** (Faster · Easier · Reliable). Inventory/Sales data is the initial domain; Replenishment Review is a multi-source demo case, not the only outcome. This is a **proposed value hypothesis**, not proven ROI.

**Data-source mapping:** In a real retailer, POS/OMS holds sales transactions, ERP/WMS holds stock/reservations, and PIM/product documents hold identity/specifications. The Week 1 local application simulates these using SQLite tables and local product files. No live POS/WMS integration or inventory freshness SLA exists.

**Tool/agent selection rule:** for a simple question route to one trusted domain function; for cross-source questions, orchestrate reviewed sales/inventory tools, preserve SKU identity and verify evidence. A deterministic tool executor is not automatically an autonomous agent; no unchecked LLM-generated SQL.


```mermaid
flowchart LR
 User[Local Web UI] --> API[FastAPI]
 API --> Graph[LangGraph StateGraph]
 Graph --> Router{Intent Routing}
 Router -->|Stock / Revenue / Top Sellers| SQL[LangChain SQL Tool]
 SQL --> DB[(SQLite / structured sales & inventory)]
 Router -->|Product Question| RAG[LangChain RAG]
 RAG --> Vec[(Chroma Vector DB)]
 Vec --> Docs[Product Knowledge: MD / PDF / DOCX / TXT / CSV / XLSX / JSON / HTML]
 SQL --> Answer[Grounded answer]
 RAG --> Answer
 Graph -.-> Trace[LangSmith Tracing]
 RAG -.-> Eval[RAGAS Evaluation]
 Answer --> API
```

## Justifications
- **Python 3.11+**: compact implementation for team/course.
- **LangGraph**: typed state, conditional route, explicit nodes. LangChain `@tool` wraps vetted parameterized SQL.
- **LangChain ChatOpenAI/OpenAIEmbeddings + Chroma**: one OpenAI-compatible base URL and key, with separate chat and embedding model identifiers; full-mode product vector RAG.
- **SQLite**: reproducible stock/order sales; read-only query connection, aggregate in SQL.
- **FastAPI + HTML/JS**: browser demo without React buildchain.
- **LangSmith**: enable traces via API key in full mode; telemetry is hosted even though application runs local.
- **RAGAS**: faithfulness and answer relevancy on product RAG with LLM judge in separate evaluation script.
- **pytest**: deterministic SQL and business calculation tests distinct from RAGAS.

## Contracts
`stock`: on_hand, reserved, available=on_hand-reserved, updated_at per location. `revenue`: completed orders only, line-level discount applied, before returns. `top`: monthly units sold. `product`: source-addressable multi-format knowledge documents; never use those docs for real-time stock.

## Pattern demonstrations and business UX acceptance

- **Chain:** product retrieval → evidence construction → model answer → citation verification; no separate LCEL RunnableSequence claimed.
- **Router + Agent:** classify natural-language intent and dispatch a Sales/Inventory/Product specialist (full-mode execution must be verified separately).
- **Subagent + Custom Workflow + Skill:** Supervisor coordinates Sales and Inventory subagents for a reviewed top-seller replenishment case, using approved business definitions.
- **Handoff:** Sales → Inventory follow-up; flexible referents like “the first one” / “what about Hanoi?” are **not yet fully implemented or accepted**.
- **Business measurement:** compare **end-to-end task time**, **interaction steps**, **post-task ease rating** and **answer correctness** against equivalent human-operated tools. Current synthetic pilot lacks a structured ease-of-use measurement, and there is no real retailer baseline.

## Planned extensions
**W2** Freshness routing (real time/15min/hourly/daily), governed KPI semantic layer, Inventory/Order MCP, customer memory, hybrid rerank rewrite, per-source answer report. **W3** HITL for pricing, RLS, KPI alerts, LangFuse, DeepEval, cost, PromptOps, governance and security. **W4** Inventory Search, Fulfilment Optimisation, Customer Context, Dynamic Pricing, Order Management, A2A coordinator, verification, deep report and approval workflow.

## Limitations
Azure configuration isolation was tested with mocks and deterministic offline business logic was tested; real Azure + full LangGraph/Chroma/RAGAS/LangSmith integration awaits installation and credentials. LangSmith may be disabled until its API key is created. No unverified capability is claimed as PASS. No auth/security yet. No autonomous order/pricing actions Week 1.

# Week 1 FDE Extension: Router, Subagent, Handoff, Skill, Session Memory

## Business case and FDE approach
**Hypothesis:** Store operators switch between sales ranking, stock by location, and product manuals to decide which bestsellers merit replenishment review. This is a synthetic scenario, *not validated via customer interviews*.

- **AS-IS:** manual report reconciliation across sales, inventory and product documents.
- **TO-BE:** a multi-agent conversational assistant performs read-only cross-domain analysis, shows decision evidence, and remembers each conversation.
- **Non-goals:** creating purchase orders, changing prices, authenticating users, accessing real ERP, or predicting future demand.
- **Success checks:** four baseline questions; cross-domain decision; sales→inventory handoff; follow-up product resolution; session isolation; delete history.

## Roles and four agent patterns

```mermaid
flowchart TD
 U[User] --> UI[UI and local session API]
 UI --> R[LangGraph Router]
 R --> S[Sales Agent]
 R --> I[Inventory Agent]
 R --> P[Product RAG Agent]
 R --> V[Retail Supervisor]
 S -->|Command handoff, follow-up stock| I
 V -->|tool delegation| SS[Sales Subagent StateGraph]
 V -->|tool delegation| IS[Inventory Subagent StateGraph]
 SS -->|scoped result| V
 IS -->|scoped result| V
 SK[Allowlisted on-demand skills] -.-> S
 SK -.-> I
 SK -.-> P
 SK -.-> V
 DB[(SQLite Chat Sessions)] <--> UI
```

**Router:** LLM structured intent classification with deterministic fallback; a typed LangGraph `Command` selects a specialist. `route_fallback` makes fallback visible.

**Subagent:** Supervisor calls two *isolated* LangGraph subgraphs through LangChain `@tool` wrappers. They return sales and inventory evidence to the supervisor. Subagents cannot mutate inventory.

**Handoff:** Following a Sales Agent turn, a stock follow-up starts at Sales Agent and executes `Command(goto='inventory_agent', update={...})`. This is control transfer, not a mere label. `handoff` is returned to UI.

**Skill:** Four allowlisted Markdown business instructions are loaded on demand by agent type from `retailiq/skills/`. Product Agent incorporates grounded-answer skill text into its model prompt. For read-only SQL roles, vetted function and documented rules bind tool access; do not treat RAG documents as executable skills.

## Session management

Local chat history stored separately from inventory database in `data/chat_sessions.sqlite3` (ignored by Git). `sessions` row stores UUID, title, active agent, timestamps; `messages` table stores typed user/assistant turns. History is bounded to last 12 messages for agent context. A request without `session_id` is stateless and backwards-compatible.

| Method | API | Purpose |
|---|---|---|
| POST | `/api/sessions` | New UUID session |
| GET | `/api/sessions` | List 50 most recent conversations |
| GET | `/api/sessions/{uuid}` | Read messages |
| DELETE | `/api/sessions/{uuid}` | Remove session and messages |
| POST | `/ask` | Accept `question` and optional `session_id` |

Browser stores **only active session UUID** locally; server stores messages. No cookies or credential values in UI. **Security caveat:** local demonstration is unauthenticated, so do not expose this service to network or production.

## Sample guided demo

1. **New chat** → “Which products are top sellers?” → Sales Agent.
2. **Same chat** → “How many units of the top seller are in stock?” → Sales→Inventory Handoff; uses SKU from ranked data.
3. **New chat** → “Tell me about USB-C GaN Charger 65W” → Product Agent and product grounding skill; live mode requires Chroma embeddings.
4. **Same chat** → “What about its stock?” → context-resolved SKU, Inventory Agent.
5. **New chat** → “Which top seller needs a replenishment review based on stock?” → Supervisor, two subagents, heuristic rule.
6. Switch sessions and reload page; show separate histories. Delete the test chat.

## Validation and limitations

- `pytest` offline regression validates APIs, SQL, graph-independent routing, session persistence and skill policy.
- `tests/test_langgraph_smoke.py` requires real installed LangGraph; CI installs it and tests compiled graph with a stub model and deterministic SQL tools.
- **Not yet verified with external LLM, Chroma embedding, RAGAS judge or LangSmith trace**. Do not present these as completed E2E until tested with valid credentials.
- No multi-tenant authorization, history summarization, purchase order approvals or production load testing. SKU resolution uses simple name matching and should be tightened in later iterations.

# Week 1 — Structured Logging & Observability Acceptance

## Implemented

Request path: `FastAPI middleware (request_id) → chat session → LangGraph/router → specialist agent → SQL/vector/LLM tools → response`. The same `request_id` is propagated by context variables and returned as `X-Request-ID`. `session_id` distinguishes chat conversations. Offline local paths log events marked `execution_mode=offline`.

Two distinct observability channels:

- **Local application logs:** bounded, rotating JSONL file; redacted error stack *locations*; read-only local UI with filters by current chat, last request, severity. Source files: `retailiq/observability.py`, `retailiq/api/logs.py`, `web/index.html` and `web/assets/app.js`.
- **LangSmith tracing:** separate provider-backed instrumentation, activated only with valid `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true`. This integration **still requires a live E2E run**, and local JSONL events are not equivalent to LangSmith traces.

## Example event (illustrative, not from a live model run)

```json
{"timestamp":"2026-10-28T07:35:00.000+00:00","level":"INFO","event":"tool.sql.completed","request_id":"9fa4c51712254f3b9669c36602f1670a","session_id":"a30db1a5-b55d-4cb9-bcae-e9c6a40bd765","agent":"inventory_agent","tool":"inventory_analytics","duration_ms":18.62,"status":"success","execution_mode":"full"}
```

## Test requirements

1. GET `/api/logs` returns only allowed fields. Invalid limit and severity are rejected.
2. A successful `/ask` response has matching `X-Request-ID` and `request_id` body.
3. Subsequent questions in the same session log `agent.routed`, `tool.offline_lookup`, and `agent.handoff` in offline tests; these are not mistaken for compiled LangGraph traces.
4. A controlled exception produces 503 with no exception message or secret, while a private JSONL record contains `error_type` and stack frame locations; UI hides the stack.
5. Client addresses other than loopback are refused access to the logs API.
6. `test_observability.py` regression tests protect against accidental prompt/key logging.

## Limits

Local logs are not an immutable compliance audit trail; there is no user auth, role-based row-level security, centralized indexing, token-based pricing, or remote trace evidence. Instrumentation is a Week 1 harness development demo. For real deployments add authentication, PII classification, deletion/retention policy, an observability backend and real LangSmith traces.

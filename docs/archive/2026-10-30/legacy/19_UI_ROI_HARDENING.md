# RetailIQ — UI/Response and Cost/ROI hardening

**Date:** 2026-10-28. **Scope:** local-only Week 1 read-only RetailIQ. No new agents, cloud deployment or production authentication.

## Evaluation/CI repair

- A source-inspection test previously required an exact string for an `AsyncOpenAI(...)` call and failed on innocuous whitespace changes.
- The test now parses Python AST and checks that exactly one `AsyncOpenAI` call receives `cfg.base_url` and `cfg.api_key`.
- This fixes a **test defect**, not proof that a real paid RAGAS provider works.
- The evaluation module's complete/provider-backed-report gate remains separate from deterministic regression coverage.

## UI/response boundary

| Contract | Implementation | Regression |
|---|---|---|
| Untrusted Markdown as inert DOM | Existing `textContent` / `createTextNode`; link parser restricts to http(s), rejects URL credentials and oversized/whitespace-wrapped links | `tests/frontend_format.test.cjs`: XSS, malicious links |
| KPI computed only from valid structured SQL evidence | Safe integer only, no coercion, no invalid/missing rows, no unsafe aggregate overflow | Malformed/NaN-like/overflow and excessive records |
| Never present partial totals as complete | For >200 evidence records, skip aggregate KPI instead of summing a truncated prefix | 201-record test |
| Negative revenue visible without misleading zero-based bar | Permit signed integer revenue total but omit positive-only bars for a negative row | Negative refund/channel test |
| Bounded source metadata | At most 100 contexts consulted, eight visible source chips, 300 chars per source | Large malicious citation set |
| Bounded SSE consumption | Up to 2 million decoded chars, 65,536-char frames and 512 data events; cancel reader on malformed/overbudget stream | Chunk-split CRLF, oversized frame, event flood |
| No dynamic `innerHTML` on response completion | Construct status dot using native DOM nodes | Existing Python UI structural tests plus Node frontend tests |

**Semantics:** The SSE limits bound what the browser accepts; they do not enforce a whole-workflow deadline or abort synchronous provider execution. The progress stream may still fail if the browser or network disconnects. The result renderer does not claim facts that are missing or invalid in SQL/RAG evidence.

## Cost/ROI boundary

- Validate direct domain calls as carefully as `/api/roi/estimate`: finite values, correct integer counts, no booleans, nonnegative values and the documented API upper bounds.
- Validate **all** token/rate assumptions before producing a financial report; no `NaN` or `Infinity` silently propagates from direct calculations.
- Keep zero-workload and no-positive-net-payback semantics explicit: `payback_months=null`; for `build_cost_vnd=0`, `year_one_net_roi_percent=null` to avoid division by zero.
- Prevent double counting: `monthly_operating_cost_vnd` is an all-in operating assumption; token USD cost stays an informational breakdown and is **not** subtracted again.
- `tests/test_roi_module_hardening.py` checks invalid direct inputs, invalid token assumptions, public API 422s, zero cases and large finite scenarios.

## Test and acceptance gates

Run:

```bash
python -m scripts.seed
RETAILIQ_REQUIRE_LANGGRAPH=true python -m pytest -q -rs
node --test tests/frontend_format.test.cjs
```

**Evidence gate:** A green GitHub Actions run for the PR **head SHA** is required before marking deterministic tests PASS. This document intentionally does not invent a test count or claim that a local screenshot / full remote provider / RAGAS evaluation ran.

**Residual risks:** Real-browser accessibility/performance testing, concurrent browser tabs, malicious spreadsheet import differences, production CSP/auth/RBAC, network fault testing, time-to-first-token and p95 latency, RAGAS/LangSmith live tracing, per-model/token usage metering, FX conversion and independently measured business ROI remain unverified. All financial outputs are illustrative synthetic scenarios.

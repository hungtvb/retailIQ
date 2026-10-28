# RetailIQ Week 1 — Live Agent Execution in Chat

## FDE decision

Retail operators should follow how the agent arrives at an answer **in the same view as the answer**. The existing Execution Logs tab is useful for retrospective diagnostics but hides the agent workflow during demos. A per-turn live event timeline improves explainability.

## Runtime design

```
Browser / AI Assistant
  POST /ask/stream (fetch + ReadableStream)
    → FastAPI StreamingResponse (SSE)
      → per-request worker, bounded queue, context-scoped event sink
        → existing log_event() allowlist + rotating JSONL
          → LangGraph / offline fallback → Agent → Skill → Tool → Handoff
        → event: log (safe metadata for this request only)
        → event: result (final answer, persisted once)
        → event: done
```

The stream is emitted by **real backend execution events**, not simulated client-side progress. Request IDs correlate in-chat stream messages with persistent JSONL and the separate log viewer. Each stream has an isolated queue and context sink; no global cross-session broadcast occurs.

## UX

- Answer on the left, live timeline on the right in desktop; stacked on mobile.
- While executing, active indicator pulses and events append with timestamps/durations.
- On success, answer is shown and the timeline marks COMPLETE.
- On failure, ERROR is shown without fabricating an answer or persisting a partial conversation turn.
- Detailed source records remain in a collapsed section; separate Execution Logs tab retains filters.
- ARIA polite updates and reduced-motion preference are supported.

## Privacy, limitations and tests

Log metadata is allowlisted; prompts, credentials, response bodies and stack traces are not streamed as *log* events. The final user-facing chatbot answer is sent only in `event: result`. This transports **execution events**, not token-by-token LLM output. No authentication or tenant isolation is implemented in the local training demo. Do not expose it publicly.

`tests/test_chat_stream.py` tests SSE ordering, correlated request/session IDs, cross-session isolation, handoff, error handling, secret redaction, invalid input and early event delivery while the agent is still blocked. Chromium UI validation was performed using a TestClient bridge (not direct browser network navigation); real chunked HTTP SSE was separately verified against Uvicorn. LangSmith and Azure full-mode E2E remain unverified.

## Run

```bash
python -m scripts.seed
python -m pytest -q
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Ask “Which products are top sellers?” then “How many units of the top seller are in stock?” to see `agent.handoff` appear in the inline timeline.

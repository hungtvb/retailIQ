# Week 1 Demo Script — 6 minutes

| Time | Segment | On-screen action |
|---|---|---|
| 0:00–0:45 | Business domain | Explain omnichannel Electronics retailer and inventory/report pain points |
| 0:45–1:30 | Architecture | Graph: Intent → SQL tool or Product RAG |
| 1:30–2:15 | Stock | Ask AlphaBook stock, show 3 locations, distinguish on-hand / reserved / available |
| 2:15–3:00 | Revenue | Ask this month's revenue, show online/store breakdown and KPI formula |
| 3:00–3:40 | Top sellers | Ask top sellers by completed-order units sold |
| 3:40–4:30 | Product RAG | Ask about 65W charger; show source and vector retrieval in **full mode** |
| 4:30–5:20 | Evaluation | Show real LangSmith trace and RAGAS scores if available; otherwise disclose not yet run |
| 5:20–6:00 | Roadmap | Explain additions in W2, W3 and mandatory W4 agents |

## Preflight
Follow `docs/05_Huong_dan_OpenAI_Compatible_VI.md`: configure the shared OpenAI-compatible `.env`, run `python -m scripts.check_openai` then optionally `--live`, seed with `python -m scripts.seed`, run `pytest -q`, then `uvicorn retailiq.api:app --host 127.0.0.1 --port 8000`. Open browser at http://127.0.0.1:8000. The checked-in `.env.example` selects full mode. Without a `.env` setting for `RETAILIQ_MODE`, the application falls back to offline mode. Full mode needs its dependencies and provider credentials; until a live E2E run, it remains unverified. Do not describe offline mode as LangGraph or vector RAG.

## Demo definitions
As-of fixed 2026-10-28 for seed repeatability. Net revenue excludes taxes/shipping/returns. Stock available is on_hand minus reserved, not on_hand alone.


## Official checklist presentation (additional slides)

Use `slides/RetailIQ_Flezi_Week1_Checklist_Aligned.pptx` for the graded demo. The additional slides cover:
- FDE: domain discovery → scoped prototype → feedback, with synthetic-data disclosure
- 5 harness layers and corresponding RetailIQ modules
- Router and custom-workflow patterns implemented; chain/agent/subagent/handoff/skill distinctions
- Token-based cost model and illustrative 3.75-month payback (not real business results)
- 43 local tests, open full-mode E2E, RAGAS and LangSmith verification gates

Present the pattern comparison and ROI slides quickly; reserve most demo time for the four questions and evidence. If LangSmith/RAGAS traces are unavailable, state they are not yet verified rather than presenting fabricated screenshots or scores.

## Clean setup, mode selection, reset, and troubleshooting

This runbook is for a local training demo. It assumes Python 3.11+, a shell, and access to the repository. Do not expose the unauthenticated app on a public interface.

### 1. Create a clean environment

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-full.txt
cp .env.example .env
```

For **full mode**, edit `.env` locally and set `RETAILIQ_MODE=full`, `OPENAI_BASE_URL`, and `OPENAI_API_KEY`. Confirm `CHAT_MODEL` and `EMBEDDING_MODEL` match the provider's model/deployment names. LangSmith needs its own local `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true`.

For the **offline fallback**, install `requirements-offline.txt` and set `RETAILIQ_MODE=offline` in `.env`. Offline mode uses deterministic SQL and lexical document retrieval; it does not execute LangGraph or Chroma vector search and cannot satisfy the full Week 1 integration gates.

### 2. Seed and check configuration

```bash
python -m scripts.seed
python -m scripts.check_openai
```

`python -m scripts.seed` deletes and recreates `data/retailiq.sqlite3`, then regenerates synthetic product documents and demo cases. Back up local edits before running it. It does not reset chat sessions, logs, or the Chroma index.

In full mode, validate credentials with one real chat and one embedding request:

```bash
python -m scripts.check_openai --live
python -m scripts.index_rag --dry-run
python -m scripts.index_rag
```

`--dry-run` parses/chunks local knowledge files without an API call. The non-dry run sends embedding requests and writes the local Chroma index under `.chroma/`; provider usage may incur cost. In offline mode, do not run the network indexing command.

### 3. Run and smoke-check the app

```bash
python -m pytest -q
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, then check `GET /health`. Ask the four questions listed above. Confirm the answer's `mode`: offline is labeled `OFFLINE deterministic fallback — not LangGraph/VectorDB`; full mode reports the LangGraph path. A full-mode product answer should include its retrieved source in `contexts`.

For Week 1 acceptance, QA must also capture a real LangSmith trace and a real RAGAS result as described in [the traceability matrix](14_Requirements_Traceability.md). A successful local test run or `--dry-run` is not that evidence.

### 4. Reset and teardown

- Stop Uvicorn with `Ctrl+C`.
- To restore the synthetic retail fixture, run `python -m scripts.seed` after backing up any custom `data/retailiq.sqlite3` content.
- To erase local chat sessions, stop the app and delete `data/chat_sessions.sqlite3` (or the file selected by `RETAILIQ_CHAT_DB`). This permanently deletes saved demo conversations.
- To clear local diagnostics, stop the app and delete files in `data/logs/` (or the configured `RETAILIQ_LOG_FILE` and rotated backups).
- To rebuild vector data, stop the app and remove `.chroma/`, then run `python -m scripts.index_rag`. This deletes the local index and requires re-embedding the knowledge files.
- Keep `.env` local. Do not include keys in demo artifacts.

### Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Full mode reports missing configuration | `.env` absent/blank or not loaded before startup | Confirm mode and provider variables are set locally; restart Uvicorn. Never paste values into logs/issues. |
| Provider reports model/deployment not found | Azure deployment or gateway model identifier differs from defaults | Set `CHAT_MODEL` / `EMBEDDING_MODEL` to deployed names; rerun `python -m scripts.check_openai --live`. |
| Chat works but product search/index fails | Embedding deployment mismatch, provider/network issue, or unreadable source | Run `python -m scripts.index_rag --dry-run`; review parse errors; confirm model and credentials; retry live indexing. |
| Product answer is missing or irrelevant | Source outside configured folders, stale index, or weak retrieval | Check dry-run file/chunk counts and source paths; allow full-mode sync or rebuild `.chroma/`; review returned `contexts`. |
| No LangSmith trace appears | Tracing disabled, key missing/invalid, or request ran offline | Use full mode, set tracing true and the separate local key, restart, issue a real request, and check the configured project. |
| RAGAS command fails | Full dependencies/provider credentials missing or judge call failed | Install `requirements-full.txt`, run provider live check, rerun `python -m scripts.eval_ragas`, and report failures without inventing a score. |
| Session not found | Selected session was deleted or its ID is invalid | Create/select a session through the UI; the API returns `404` for a missing session. |
| Port 8000 is already in use | Another local process owns the port | Stop the other demo process or choose a free local port; keep host bound to `127.0.0.1`. |

### Operating and security boundary

The demo has no authentication, user roles, tenant isolation, production retention policy, or row-level security. Chat messages are stored locally. The logs endpoint is loopback-only and is not a compliance audit trail. Do not bind to `0.0.0.0`, publish through a tunnel/reverse proxy, or use customer/employee personal data. See the [risk register](15_Risk_Register_and_Document_Governance.md).

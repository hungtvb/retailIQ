# RetailIQ — Local E2E & Benchmark Evidence (2026-10-28)

## Scope

These tests ran **real HTTP/SSE through a localhost Uvicorn process** and, separately, **real compiled LangGraph through FastAPI with mocked model and retrieval provider**. SQLite and business SQL are real against deterministic synthetic fixtures. No cloud LLM, remote Chroma embeddings, LangSmith tracing, actual browser or production deployment was exercised.

## Verified CI evidence

- [Regression run 40718345060](https://github.com/hungtvb/retailIQ/actions/runs/40718345060): **260 Python tests PASS, 12 Node frontend tests PASS**.
- [E2E / benchmark run 40718346251](https://github.com/hungtvb/retailIQ/actions/runs/40718346251): **3 mocked-provider compiled LangGraph ASGI E2E PASS; 5 real localhost TCP E2E groups PASS; 400/400 measured HTTP calls successful**.
- [Download structured JSON evidence](https://github.com/hungtvb/retailIQ/actions/runs/40718346251/artifacts/12828233391). GitHub artifact retention: 14 days.
- Both CI results apply to tested branch SHA b278e2195c6de02475d6ff0d24ce1dc8ee31295a.
- An initial quality run failed because the test harness read an HTTP response header case-sensitively. The harness was fixed; the fresh runner above passed.

## E2E checks

1. Live localhost health/UI/static assets/ROI routes.
2. Real TCP SSE started/log/result/done, correlated request ID, top-seller sales -> inventory handoff, session persistence of four ordered messages and deletion.
3. Stock, revenue, top sellers, offline lexical product knowledge and replenishment review. Revenue is checked against an independent SQLite completed-order query, and stock arithmetic against on_hand minus reserved.
4. Eight concurrent independent sessions each persist one exact user/assistant pair.
5. 422/404/403 invalid requests, Host restriction, redacted local observability endpoint.
6. Source retail SQLite fixture checksum unchanged after E2E and benchmark.
7. Additional mocked-provider compiled LangGraph ASGI tests exercise all five business intents, real SQLite checkpoint, specialist subgraph, and failed provider rollback; mock router/answer/retrieval services are **not** live-provider evidence.

## Benchmark metrics from run 40718346251

Ubuntu GitHub Actions, Python 3.11, one Uvicorn process, 50 calls per scenario, 3 warmups excluded, fresh localhost TCP request per operation. No real LLM time. Client-observed latency, percentiles interpolated.

| Endpoint | Concurrency | p50 ms | p95 ms | p99 ms | Requests/s | Failures |
|---|---:|---:|---:|---:|---:|---:|
| GET /health | 1 | 1.059 | 1.134 | 1.408 | 879.93 | 0/50 |
| GET /health | 4 | 4.169 | 5.161 | 5.609 | 930.42 | 0/50 |
| GET /health | 8 | 7.730 | 9.899 | 10.307 | 960.86 | 0/50 |
| GET /health | 16 | 14.956 | 17.290 | 17.765 | 947.05 | 0/50 |
| POST /ask stock | 1 | 3.591 | 3.786 | 3.984 | 270.42 | 0/50 |
| POST /ask stock | 4 | 20.392 | 24.753 | 26.135 | 190.08 | 0/50 |
| POST /ask stock | 8 | 43.289 | 48.212 | 50.122 | 184.01 | 0/50 |
| POST /ask stock | 16 | 91.848 | 103.734 | 108.224 | 171.36 | 0/50 |

### Interpretation

Local stock latency rises with concurrency while throughput plateaus or decreases. Runner variation is substantial: successful run [40718207785](https://github.com/hungtvb/retailIQ/actions/runs/40718207785) measured stock concurrency-16 p95 53.072 ms, versus 103.734 ms here. Only 50 samples per tier were used; p99 and request rates are exploratory, **not a production SLA**.

## How to reproduce

Install Python 3.11:

~~~bash
python -m pip install -r requirements-offline.txt 'langgraph>=1,<2' 'langchain-core>=1,<2' 'langchain>=1,<2' 'langgraph-checkpoint-sqlite>=3,<4'
python -m scripts.seed
RETAILIQ_REQUIRE_LANGGRAPH=true python -m pytest -q -rs
node --test tests/frontend_format.test.cjs
python -m pytest -q -rs tests/test_mocked_full_graph_e2e.py
python -m scripts.quality_gate --samples 50
~~~

JSON report: data/quality_reports/e2e_benchmark.json, with an artifact uploaded by the quality-gate GitHub Actions workflow. The runner now seeds an isolated temporary SQLite fixture and leaves the project data file and product documents untouched. The benchmark numbers above are historical results from the linked CI run; rerun the workflow to capture results for the updated runner.

## Acceptance and residual risk

**PASS on the linked PR #3 run:** unit/regression; mocked full-graph integration; localhost Uvicorn API/SSE E2E; synthetic 400-request performance sample. The new runner checks that its temporary business fixture stays unchanged during requests.

**NOT VERIFIED:** live LLM tool-selection quality; real Chroma embedding/retrieval; RAGAS semantic metrics; remote LangSmith traces; real browser visual/accessibility; 30-minute soak / memory leaks; multi-process/distributed concurrency; public production auth; sustained p95 latency and production traffic SLA.

# RetailIQ

RetailIQ is a natural-language decision-support assistant for the fictional B2C retailer **Fiction Retail**.

**Current implementation:** the pinned Fiction data release has a verified **read-only SQL foundation (M0)**. The interactive chat, LangGraph, MCP and RAG paths still run on the separate **legacy retail demo**, not Fiction. UC-01 integration is planned, not available as an end-to-end feature.

## Quick start — Fiction data (implemented M0)

1. Use **Python 3.12**. Get the `fiction-retail-unified-v1.0.0` SQLite file (`data/fiction_retail.sqlite`) from [fiction-retail](https://github.com/hungtvb/fiction-retail) using Git LFS, or a byte-identical local copy.
2. Copy the file to `data/fiction/fiction_retail.sqlite` in this repo. Keep the committed `data/fiction/manifest.json` unchanged.
3. Run from the repository root:

```sh
python -m scripts.verify_fiction_runtime --db data/fiction/fiction_retail.sqlite --manifest data/fiction/manifest.json
```

This verifies the Fiction snapshot and independent SQL scenarios. **It does not start a Fiction-powered chat.** See [Fiction runtime instructions](docs/FICTION_RUNTIME.md).

## Run the existing chat demo (legacy only)

Requires Python 3.12, Node.js and an OpenAI-compatible chat/embedding endpoint. Create/activate a Python 3.12 virtual environment, then copy `.env.example` to `.env` (PowerShell: `Copy-Item .env.example .env`; Bash: `cp .env.example .env`). Set `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `CHAT_MODEL` and `EMBEDDING_MODEL` for your provider.

```sh
python -m pip install -r requirements-full.txt
python -m scripts.seed
python -m scripts.index_products
npm --prefix frontend install
npm --prefix frontend run build
python -m uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/workspace` (or the original interface at `/`). **The seed/index commands recreate or index only the legacy `EL-###`/VND fixture, never Fiction.** Back up customized legacy fixture data before seeding; never commit `.env`.

## Documentation

[Documentation index](docs/README.md) · [Architecture](docs/ARCHITECTURE.md)

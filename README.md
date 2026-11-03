# RetailIQ

RetailIQ is an AI-powered retail decision-support assistant for exploring inventory, sales, and product knowledge through natural language.

## Quick Start — existing legacy chat

**Prerequisites:** Python 3.12, Node.js, and an OpenAI-compatible API endpoint.

**macOS / Linux (Bash):**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

**Windows (PowerShell):**
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Edit `.env` with your `OPENAI_BASE_URL` and `OPENAI_API_KEY`. Set `CHAT_MODEL` and `EMBEDDING_MODEL` to your provider's model/deployment names when needed. Do not commit `.env`.

**Then, in either shell:**
```text
python -m pip install -r requirements-full.txt
python -m scripts.seed
python -m scripts.index_products
npm --prefix frontend install
npm --prefix frontend run build
python -m uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/workspace**. The existing UI is available at `/`.

The commands above run the **existing legacy** `EL-###`/VND chat demo using the seeded retail fixture. They do **not** switch chat, LangGraph, MCP or RAG to Fiction Retail.

## Fiction Retail local data (M0 only)

RetailIQ also has a separate, **implemented read-only Fiction SQL foundation** (not yet wired to `/ask`). Copy the `fiction-retail-unified-v1.0.0` SQLite object from Fiction Retail Git LFS to `data/fiction/fiction_retail.sqlite`; keep the pinned `data/fiction/manifest.json` from this repo. Verify the exact local release:

```bash
python -m scripts.verify_fiction_runtime --db data/fiction/fiction_retail.sqlite --manifest data/fiction/manifest.json
```

See [Fiction runtime and integrity contract](docs/FICTION_RUNTIME.md) for import details and limitations. Do **not** run `scripts.seed` to provision Fiction.

## Documentation

See [Project Documentation](docs/README.md).

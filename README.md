# RetailIQ

RetailIQ is an AI-powered retail decision-support assistant for exploring inventory, sales, and product knowledge through natural language.

## Quick Start

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

## Documentation

See [Project Documentation](docs/README.md).

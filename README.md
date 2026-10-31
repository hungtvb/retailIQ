# RetailIQ

RetailIQ is an AI-powered retail decision-support assistant for exploring inventory, sales, and product knowledge through natural language.

## Quick Start

**Prerequisites:** Python 3.12, Node.js, and an OpenAI-compatible API endpoint for full mode.

```bash
python -m venv .venv
# Activate the virtual environment: source .venv/bin/activate (macOS/Linux)
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-full.txt
# Copy .env.example to .env and configure OPENAI_BASE_URL and OPENAI_API_KEY
python -m scripts.seed
python -m scripts.index_products
cd frontend && npm install && npm run build && cd ..
python -m uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/workspace**. The existing UI is also available at `/`.

## Documentation

See [Project Documentation](docs/README.md).

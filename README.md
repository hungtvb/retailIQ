# RetailIQ

RetailIQ is an AI-powered retail decision-support assistant for exploring inventory, sales, and product knowledge through natural language.

## Quick Start — local authenticated workspace

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
python -m scripts.manage_users create --username analyst01 --role analyst
python -m scripts.manage_users create --username manager01 --role manager
npm --prefix frontend install
npm --prefix frontend run build
python -m uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/workspace** and sign in with the local Analyst or Manager account created above. Provisioning prompts for passwords without echoing them; there are **no default credentials**. Keep the server on loopback only. The existing historical demo UI remains at `/` but has no separate login screen.

The seed and index commands provide the independent legacy `EL-###` sample for basic chat. Fiction Retail case/stock capabilities use their **own pinned read-only source**, not the synthetic seed. They are intentionally separate.

## Fiction Retail local data

RetailIQ supports verified Fiction stock, order and historical UC-01 case investigation through the `/ask` full-mode path; local Manager approval records are **not warehouse transactions**. Copy the `fiction-retail-unified-v1.0.0` SQLite object from Fiction Retail Git LFS to `data/fiction/fiction_retail.sqlite`; keep the pinned `data/fiction/manifest.json` from this repo. Verify the exact local release:

```bash
python -m scripts.verify_fiction_runtime --db data/fiction/fiction_retail.sqlite --manifest data/fiction/manifest.json
```

See [Fiction runtime and integrity contract](docs/FICTION_RUNTIME.md) for the pinned manifest, policy documents and exact release setup. The Fiction paths must be configured for full-mode use; do **not** run `scripts.seed` to provision Fiction. Human review affects only the application SQLite database.

## Documentation

See [Project Documentation](docs/README.md).

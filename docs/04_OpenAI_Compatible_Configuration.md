# Provider configuration — One OpenAI-compatible endpoint

This edition uses **one URL and one key for both chat and embeddings**. It works with Azure OpenAI **v1**, OpenAI API and compatible HTTPS gateways.

```dotenv
OPENAI_BASE_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1/
OPENAI_API_KEY=YOUR_LOCAL_API_KEY
CHAT_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

Only the first two are mandatory fields; `CHAT_MODEL` and `EMBEDDING_MODEL` have the defaults shown. For Azure, supply the *actual deployment names* if different from defaults. A single endpoint/key does not imply a single model or deployment.

Azure resource-root `https://RESOURCE.openai.azure.com/` is automatically converted to `/openai/v1/`. Other gateway paths are preserved as provided. Do not pass a full `/chat/completions` or `/embeddings` request URL. Legacy classic Azure endpoints requiring API version are not covered by the simplified interface.

Run:

```bash
python -m scripts.check_openai
python -m scripts.check_openai --live
python -m scripts.seed
python -m pytest -q
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Troubleshooting: 404 = model/deployment not recognized; 401/403 = wrong key/access/endpoint; 400 = model or API compatibility; 429 = quota or throttling. Do not paste raw errors or URLs that may carry sensitive deployment information.

LangSmith requires a **separate LangSmith API key** if tracing is to be demonstrated. Without it leave `LANGSMITH_TRACING=false`. RAGAS requires working chat + embedding deployments but no separate API key.

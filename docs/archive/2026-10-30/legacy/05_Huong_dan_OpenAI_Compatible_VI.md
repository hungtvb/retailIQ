# RetailIQ Week 1 — Cấu hình một OpenAI Base URL và API key

Không cần 2 endpoint/2 key. Chat LLM và embedding dùng chung cấu hình OpenAI-compatible.

1. `cp .env.example .env` (Windows PowerShell: `Copy-Item .env.example .env`)
2. Điền hai biến bắt buộc:

```dotenv
RETAILIQ_MODE=full
OPENAI_BASE_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1/
OPENAI_API_KEY=YOUR_LOCAL_API_KEY
```

3. Code có hai giá trị mặc định: `CHAT_MODEL=gpt-4o-mini` và `EMBEDDING_MODEL=text-embedding-3-small`. **Nếu Azure deployment của anh có tên khác, đổi 2 biến này thành đúng deployment names.** Hai tên này không phải key hay endpoint bổ sung.
4. Azure OpenAI v1 không cần `api-version`. Có thể cung cấp root `https://RESOURCE.openai.azure.com/` — ứng dụng tự thêm `/openai/v1/`. Với gateway OpenAI-compatible khác, giữ chính xác URL base của provider. Không dùng URL request cụ thể như `/chat/completions`.

Chạy local:

```bash
pip install -r requirements-full.txt
python -m scripts.check_openai          # không gọi API
python -m scripts.check_openai --live   # 2 API requests thật: chat + embedding
python -m scripts.seed
python -m pytest -q
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`.

Với yêu cầu RAGAS: `python -m scripts.eval_ragas` (có phát sinh chi phí). LangSmith là yêu cầu trong Week 1; nếu chưa có LangSmith key, có thể chạy demo local nhưng **chưa hoàn thành hạng mục tracing**.

**Không gửi key vào chat, commit Git hoặc screenshot.** `.env` được gitignore. Chỉ chạy server trên `127.0.0.1`.

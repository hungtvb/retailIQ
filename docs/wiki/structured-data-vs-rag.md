# Structured Data vs RAG: nguồn nào được quyền trả lời?

**Problem:** "EL-003 còn bao nhiêu?" và "EL-003 hỗ trợ chuẩn sạc gì?" đều là câu hỏi về sản phẩm, nhưng cần **hai loại evidence khác nhau**. Embedding similarity hữu ích cho tài liệu tự do, nhưng không đảm bảo SKU, kỳ, phép tính hay trạng thái đơn được giữ chính xác.

## Concept trước khi chọn tool

- **Structured query** trả lời từ bảng có cột và semantic rõ: SKU, location, order status, period. Dùng SQL parameterized, phép tính deterministic và validation; muốn so sánh số phải dùng data oracle.
- **RAG** = retrieve nội dung liên quan → cung cấp làm evidence → generate đáp án có dẫn nguồn → validate grounding/citations. RAG không tự làm dữ liệu đúng hoặc mới.
- **Vector search** tìm đoạn gần về embedding semantics, không cam kết đúng thực thể chính xác hay timestamp.
- **Hybrid retrieval** kết hợp vector ranking và lexical evidence. RetailIQ dùng reciprocal-rank fusion và lexical re-ranking; điểm xếp hạng **không phải xác suất câu trả lời đúng**.

## Authority matrix — một câu hỏi, một nguồn đúng

| Câu hỏi | Nguồn ưu tiên | Không được suy ra từ |
|---|---|---|
| Còn bao nhiêu hàng SKU X tại HCM? | `inventory` + `locations` (SQL snapshot) | File mô tả sản phẩm hoặc vector similarity |
| Doanh thu tháng M của top seller #1? | `orders`, `order_lines` + SKU được xếp hạng **trong cùng tháng** | Giá niêm yết hoặc doanh thu toàn cửa hàng |
| SKU giá cao nhất? | `products.price_vnd` (catalog list price) | Order price đã discount hoặc văn bản RAG |
| Tương thích/đặc tính/warranty note? | Product knowledge chunk có source ID | SQL stock hoặc suy đoán của model |
| Dữ liệu mới "ngay bây giờ"? | **Refresh timestamp tin cậy** của nguồn phù hợp, nếu có | Ngày tạo order/catalog hay tên tier `live` |

Định nghĩa KPI chính xác (trừ discount trên toàn **order line**, completed orders, `on_hand-reserved`…) nằm trong [Data & API](../DATA_API.md), **không sao chép** sang Wiki.

## Alternatives & decision

- **Chỉ SQL**: đơn giản, kiểm toán tốt, nhưng kém linh hoạt khi tìm thông số trong văn bản dài.
- **Chỉ RAG**: hợp cho product knowledge; **không chấp nhận** dùng để tổng hợp money/stock hay verify freshness.
- **Text-to-SQL tùy ý của LLM**: linh hoạt nhưng tăng rủi ro query lệch điều kiện, sai semantic và chạy lệnh ngoài phạm vi. RetailIQ **không thực thi unrestricted generated SQL**.
- **SQL + document RAG (chọn)**: domain functions chịu trách nhiệm số liệu; retriever/LLM chịu trách nhiệm nội dung mô tả có nguồn. Lớp orchestration chỉ kết hợp khi nghiệp vụ cần.

## HOW — source và execution mode

- `retailiq/domain/analytics.py`, `retailiq/domain/revenue_plan.py`, `retailiq/queries.py`: semantic/validation cho price, stock, revenue, ranking; product-scoped revenue không được fallback thành store total.
- `retailiq/retrieval.py`: `offline` dùng lexical chunks; `full` chọn `vector` hoặc `hybrid` qua `RETAILIQ_RAG_RETRIEVAL`.
- `retailiq/rag/indexing.py`: parse/chunk, manifest source hash + chunk IDs; index thiếu/stale thì báo lỗi thay vì giả vờ tìm kiếm được.
- `retailiq/rag/advanced_retrieval.py`: lexical candidates phải khớp **manifest của cùng index** trước khi hợp nhất rank.
- `retailiq/rag/grounding.py`, `orchestration/agents.py`: context là **untrusted evidence**, không phải system instruction; validate `[S1]` citations, không chấp nhận references bịa.

## Trade-offs, verification và revisit

**Chi phí:** RAG full-mode cần ingest, embedding, vector index, model call, kiểm tra source và đánh giá chất lượng. Hybrid tăng số đường code nên chỉ đáng giữ nếu tập câu hỏi đánh giá cho thấy cải thiện recall/rank so với vector/lexical riêng.

**Thử lỗi quan trọng:** missing/renamed source, stale hash, prompt injection trong document, SKU không khớp, sản phẩm trùng tên, tháng khác nhau giữa ranking và revenue, kết quả retrieval không liên quan. Không coi context hiện diện là câu trả lời có căn cứ.

**Đánh giá:** `python -m scripts.audit_queries --mode offline --strict` cho SQL; `scripts/eval_retrieval.py` cho source hit@k/MRR trong đúng mode; `scripts/eval_ragas.py` đánh giá generation khi có provider. Kết quả thực tế và gate chưa hoàn thành nằm ở [Capability Ledger](../29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md).

**Official reading (đối chiếu 2026-10-31):**
- [LangChain retrieval fundamentals](https://docs.langchain.com/oss/python/deepagents/retrieval)
- [Chroma query/get and nearest-neighbor search](https://docs.trychroma.com/docs/querying-collections/query-and-get)

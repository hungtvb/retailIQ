# Context & Memory: nhớ đúng cái gì, trong phạm vi nào?

**Problem:** người dùng hỏi "top seller tháng 10" rồi hỏi "còn bao nhiêu hàng?". Câu thứ hai phụ thuộc context: **SKU nào, ranking nào, period nào, location nào**. Nhớ quá ít khiến câu trả lời sai scope; nhớ quá rộng khiến lộ dữ liệu giữa session hoặc gắn nhầm customer identity.

## Ba tầng khác nhau

| Tầng | Khái niệm | RetailIQ hiện có |
|---|---|---|
| **Conversation context** | Lịch sử gần đây để giải quyết tham chiếu/câu nối | `infrastructure.sessions.history()` giới hạn lịch sử cho chat; `orchestration/week1_graph.py` có `bounded_history()` và `resolve_followup()` |
| **Graph checkpoint** | Snapshot state theo thread để tiếp tục graph giữa các bước/lượt | Full-mode dùng `SqliteSaver`, `thread_id` theo session; checkpoint không là kho "hồ sơ khách hàng" |
| **Consented preferences** | Dữ liệu do người dùng chọn lưu, phạm vi và retention rõ ràng | `customer_session_memory` lưu các preference allowlisted khi `consent=true`, chỉ cùng session |

Theo LangGraph, **checkpointer** phục vụ state ngắn hạn theo thread; **store** có thể dùng cho long-term cross-thread memory. RetailIQ **chưa triển khai** authenticated cross-session customer identity/store. Gọi DB local là "long-term memory production" là không chính xác.

## Alternatives và quyết định

- **Gửi toàn bộ chat vào mỗi prompt**: đơn giản nhưng tốn token, tăng latency, prompt injection và nguy cơ context lẫn lộn.
- **Chỉ lấy câu gần nhất**: nhẹ nhưng không đủ để giải quyết "top seller đó".
- **Bounded context + explicit reference resolution (chọn)**: giới hạn history, trích context có liên quan, kiểm tra các constraint trước khi query.
- **Cross-session user profile**: có ích nếu đã có principal xác thực, consent, revoke/retention và ACL. **Defer** thay vì giả định session UUID là identity.

**Trade-off:** rules/heuristics cho follow-up không xử lý được mọi câu tự nhiên. Khi "top 5" không chỉ một SKU duy nhất, câu tiếp theo "nó" phải clarify hoặc chỉ rõ rank, **không được tự đoán SKU**.

## HOW — điểm vào thực tế

- `retailiq/api/http.py`: `_perform_turn()` nạp gần đây **tối đa 12 turns/messages theo helper**, session's active agent và memory *chỉ khi consented*. HTTP/SSE có concurrency guard cho cùng session.
- `retailiq/orchestration/week1_graph.py`: `followup_intent()`, `resolve_followup()`, `bounded_history()`; graph checkpoint là local single-process SQLite; xóa session phải cleanup checkpoint.
- `retailiq/infrastructure/sessions.py`: session messages, bounded local traces, `get_customer_memory()`/`save_customer_memory()`, delete cascade. Một stored trace thiếu không có nghĩa là agent không chạy.
- `retailiq/domain/customer_memory.py`: whitelist các preference an toàn, từ chối free-text PII, lưu consent rõ.
- `retailiq/api/sessions.py`: `PUT/GET/DELETE /api/sessions/{id}/memory`; caller có UUID không được coi là owner đã xác thực.

Đừng lẫn **history persisted**, **context thực sự đưa vào model**, **checkpointer** và **memory preference** — mỗi thứ có đường code và quyền truy cập khác nhau.

## VERIFY / failure cases

1. Session A và B dùng SKU/period khác nhau, follow-up không được chéo context.
2. Không có context đủ rõ → clarify, không "làm đầy" bằng kết quả toàn store.
3. `consent=false` không lưu preference; revoke phải xóa; delete session xóa dữ liệu liên quan.
4. Trường preference không nằm trong allowlist hoặc chứa PII → reject.
5. Reload/restart: chỉ những gì thực sự persisted, cùng session hợp lệ, mới có thể được lấy lại; đừng coi local UUID là secure identity.

Kiểm tra: `python -m pytest -q tests/test_customer_memory.py` và query/follow-up scenarios ở [Testing](../27_BEHAVIORAL_ACCEPTANCE_MATRIX.md). Hiện tại **không có acceptance** cho cross-user identity/memory hay authenticated authorization.

**Official reading (đối chiếu 2026-10-31):**
- [LangGraph persistence: checkpointer vs store](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangChain multi-agent: context isolation](https://docs.langchain.com/oss/python/langchain/multi-agent)

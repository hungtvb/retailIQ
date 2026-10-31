# Evaluation & Observability: điều gì thực sự chứng minh đúng?

**Problem:** một hệ thống có trace đẹp, graph nhiều node, HTTP 200 và CI xanh vẫn có thể trả **doanh thu cả cửa hàng** khi người dùng hỏi **doanh thu top seller**. Trace trả lời **đã chạy gì**; correctness oracle trả lời **có đúng không**. Cần cả hai.

## Khác nhau giữa Test, Evaluation và Trace

| Tầng | Câu hỏi cần trả lời | Ví dụ evidence |
|---|---|---|
| **Deterministic business audit** | SKU/period/location/quantity/price/discount đúng chứ? | Source fixture, independent SQL oracle, expected/actual, failed case |
| **Integration/runtime** | Tool, MCP stdio, API, session, SSE và graph thực thi thực tế chứ? | Process/transport log, request ID, browser E2E, negative case |
| **Retrieval/generation evaluation** | Đoạn tìm được phù hợp? Câu trả lời grounded và đúng trọng tâm? | Source hit@k/MRR, RAGAS faithfulness/response relevancy theo dataset |
| **Observability** | LLM/tool nào được gọi, mất bao lâu, lỗi ở đâu, tốn token bao nhiêu? | Local events và remote LangSmith trace, gắn request + commit + mode |

**RAGAS faithfulness** kiểm tra mức câu trả lời được hỗ trợ bởi contexts; **response relevancy** kiểm tra mức trả lời phù hợp câu hỏi. Cả hai **không thay** độc lập SQL oracle, xác thực quyền hay kiểm tra freshness.

## Vì sao không chỉ dùng RAGAS / một green CI?

- LLM judge có variance, phụ thuộc model, prompt, dataset, cost. Một sample nhỏ không chứng minh coverage toàn bộ câu hỏi.
- Retrieval ranking tốt không đảm bảo SQL amount hay identity chính xác; model có thể diễn đạt sai cho dù contexts đúng.
- Một graph node màu xanh hoặc `skill.selected` không chứng minh actual model/tool invocation. Cần trace sự kiện với nguồn tin cậy.
- Mọi **PASS phải ghi target commit, input, mode, expected/observed, môi trường/config và artifacts**. Kết quả cũ trên commit khác là historical evidence.

## HOW — RetailIQ hiện có những lớp nào?

- `scripts/audit_queries.py`: query acceptance với oracle; `--strict` khiến mismatch fail, tránh chỉ in báo cáo mà không ngăn regression.
- `scripts/audit_workflows.py`, `audit_edge_scenarios.py`, `audit_freshness.py`, `smoke_mcp_stdio.py`: workflow/negative/freshness/transport được kiểm thử riêng.
- `scripts/eval_retrieval.py`: đánh giá expected source, hit@k/MRR cho vector và hybrid; cần index/provider thực khi chạy live.
- `scripts/eval_ragas.py`, `retailiq/evaluation.py`: yêu cầu `RETAILIQ_MODE=full`, actual embeddings/model, kiểm tra sample scores hợp lệ và ghi report sau khi đủ cases. Đọc [dated evidence](../weeks/week-01/EVIDENCE.md) để hiểu phạm vi kết quả cũ; **không** tuyên bố current-pass.
- `retailiq/observability.py`, `api/http.py`: local rotating JSONL, request IDs, SSE **execution events** và persisted bounded traces; không phải streaming từng token LLM.
- `retailiq/core/config.py`: remote LangSmith tracing **opt-in** nếu có cấu hình/key. Local log và remote LangSmith trace là **hai nguồn evidence khác nhau**.

## Trade-offs / protocol báo cáo tối thiểu

**Ít test nhưng đúng oracle** quan trọng hơn hàng loạt unit tests chỉ mock output. Với một thay đổi doanh thu top seller, cần ít nhất: tháng cụ thể, top rank → SKU đúng kỳ, order status=completed, discount từng line, subtotal đúng, negative case kỳ/sku không rõ. Sau đó mới kiểm tra natural-language output và route.

**Định dạng kết quả nên ghi trong Issue/PR hoặc report artifact**, không mở thêm một acceptance ledger khác:

| Field | Ý nghĩa |
|---|---|
| `commit`, `timestamp`, `environment`, `mode` | Điều kiện có thể tái tạo |
| `scenario_id`, `input`, `expected`, `observed` | Business oracle; tránh chỉ `200 OK` |
| `result`, `failure_reason`, `trace_id` | PASS/FAIL và lý do, không che lỗi |
| `artifact_url`, `limitations` | Bằng chứng có thể truy xuất, scope chưa phủ |

Generated reports/screenshots/traces để ngoài Git, tránh lộ dữ liệu và repo bloat; `tests/`, fixtures và script source vẫn version-control. Kiểm tra status mới nhất theo **[Capability Ledger](../29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md)**, không theo một ví dụ trong Wiki.

## Khi nào revisit?

Chỉ bổ sung provider/model judge mới hoặc nền tảng observability khi có question/reliability gap cần đo mà công cụ hiện tại không giải quyết được. Ưu tiên tăng dataset chứa lỗi thật và phân loại error (routing, entity scope, retrieval, reasoning, source freshness) trước khi thêm framework.

**Official reading (đối chiếu 2026-10-31):**
- [LangSmith Observability](https://docs.langchain.com/langsmith/observability)
- [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation)
- [RAGAS Faithfulness](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/)
- [RAGAS Response Relevancy](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/answer_relevance/)

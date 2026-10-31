# RetailIQ Engineering Wiki

**Mục đích:** học kiến thức kỹ thuật thông qua các quyết định **thực sự đã đưa ra trong RetailIQ**. Mỗi bài trả lời: **WHY → CONCEPT → ALTERNATIVES → HOW (source) → TRADE-OFF → VERIFY → WHEN TO REVISIT**.

Wiki này **không phải** bản sao của [Requirements](../REQUIREMENTS.md), [Architecture](../ARCHITECTURE.md), [Basic/Detail Design](../DESIGN.md), [Data & API](../DATA_API.md) hay [Capability Ledger](../29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md). Nếu cần xác định contract hay trạng thái kiểm thử hiện tại, hãy đọc **tài liệu chuẩn** tương ứng. Wiki giải thích *tại sao* và *khi nào* nên thiết kế khác đi.

## Đường học theo vấn đề

| Khi đang tìm hiểu | Đọc bài | Câu hỏi tự kiểm tra |
|---|---|---|
| Phân phối câu hỏi, tool call, handoff, subagent | [Agent orchestration](agent-orchestration.md) | Khi nào chỉ cần function thay vì thêm agent? |
| Phân biệt SQL và RAG, tránh hallucination số liệu | [Structured data vs RAG](structured-data-vs-rag.md) | Tại sao vector search không phải nguồn tồn kho? |
| Chat nhiều lượt, state, consent và session isolation | [Context & memory](context-and-memory.md) | Checkpoint có đồng nghĩa long-term customer memory? |
| Tool interoperability và stdio transport | [MCP integration](mcp-integration.md) | Có MCP tool thì đã là hosted/live integration chưa? |
| Business oracle, trace, RAGAS và giới hạn bằng chứng | [Evaluation & observability](evaluation-and-observability.md) | Tại sao một screenshot hoặc CI xanh chưa đủ? |

**Cách đọc nhanh:** chọn đúng bài theo task; chỉ mở file source được chỉ tới. Không load toàn bộ Wiki vào context của coding agent. Đọc nguồn chính thức ở cuối bài khi cần kiểm tra framework/phiên bản, không dùng bài Wiki như API reference.

## Quy tắc biên soạn

1. **Code is evidence:** mọi tuyên bố "RetailIQ đã làm" phải có source path; giả định, mô phỏng, đề xuất và chưa kiểm chứng phải ghi riêng.
2. **Reasoning before ceremony:** chỉ ghi lại kiến thức và lựa chọn có trade-off đáng nhớ; không tạo một ADR/template riêng cho mỗi thay đổi nhỏ.
3. **Version-aware:** framework phát triển; đối chiếu tài liệu chính thức mới nhất trước thay đổi đáng kể. URL trong bài được kiểm tra **2026-10-31**, nhưng không chứng nhận package đã nâng cấp/kiểm thử với revision mới.
4. **Change on need:** khi một quyết định hoặc limitation thay đổi, cập nhật đúng bài và link PR/test liên quan. Tránh cập nhật Wiki vì một đổi tên biến hay formatting.
5. **Learning ≠ acceptance:** diễn giải công nghệ không phải bằng chứng thực thi. Test pass/fail theo commit và mode nằm trong [Capability Ledger](../29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md).

[Quay về mục lục tài liệu](../README.md).

# Agent Orchestration: vì sao LangGraph, khi nào không cần agent?

**Question:** "Tồn kho top seller tháng 10 thế nào?" cần xác định thứ hạng từ giao dịch, giữ nguyên SKU/kỳ rồi mới đọc tồn kho. Còn "EL-003 có bao nhiêu?" chỉ cần một phép tra cứu chính xác. Áp dụng một workflow nhiều agent cho cả hai sẽ làm tăng model calls, latency và đường lỗi.

## Concepts cần phân biệt

- **Tool**: một thao tác có input/output đã định nghĩa; `domain.analytics.inventory()` tính tồn kho bằng SQL được kiểm soát. Tool không tự nhiên trở thành "agent".
- **Router**: chọn đường thực thi theo intent/state; có thể deterministic hoặc có LLM hỗ trợ, **không đồng nghĩa nhiều agent cùng chạy**.
- **Subagent**: chuyên gia nhận subtask có scope rõ, trả kết quả cho supervisor để tổng hợp/kiểm tra.
- **Handoff**: chuyển quyền xử lý giữa các state/agent; một nhãn "handoff" trên UI **không chứng minh** control đã được chuyển.
- **Skill**: chỉ dẫn nghiệp vụ nạp khi phù hợp; nó không cấp quyền chạy SQL tùy ý hay mutation.
- **LangGraph StateGraph**: đồ thị có state và control flow rõ; có thể kết hợp step deterministic, LLM, retry và checkpoint.

Đừng gộp **workflow graph trình bày**, **LangGraph thực thi**, và **hệ thống multi-agent độc lập** thành một khái niệm.

## Alternatives và quyết định

| Cách làm | Khi tốt | Điểm yếu / quyết định RetailIQ |
|---|---|---|
| Python function + SQL | Tra cứu một nguồn, business rule cố định | **Ưu tiên** cho phép tính và kiểm chứng số liệu |
| Single LangChain agent với tools | Task có một model-driven tool loop đơn giản | Không nhất thiết cần điều khiển graph chi tiết |
| LangGraph với node/state/`Command` | Có routing, handoff, session checkpoint, các đường đi khác nhau | **Chọn cho chat full-mode**; trả giá bằng độ phức tạp state/control |
| Nhiều autonomous agents / A2A | Có ranh giới chuyên môn/độc lập và bằng chứng phối hợp thực sự | **Chưa thể khẳng định** từ năm nhãn chuyên gia trong workflow simulator |

**Nguyên tắc:** bắt đầu từ business dependency, không bắt đầu từ số lượng agent. Với câu hỏi đơn giản, một domain function đáng tin có thể là đáp án tốt nhất.

## HOW — RetailIQ thực sự chạy

- `retailiq/assistant.py`: `RETAILIQ_MODE=full` chuyển sang graph; chế độ offline dùng các function có deterministic routing, **không phải LangGraph model execution**.
- `retailiq/orchestration/week1_graph.py`: `route()` phân loại, chọn node; `build_graph()` tạo `StateGraph`; `sales_agent()` trả `Command(goto='inventory_agent')` khi phù hợp. `SqliteSaver` phục vụ checkpoint theo session.
- `retailiq/orchestration/agents.py`: `sales_analysis()`, `inventory_analysis()`, `product_analysis()` dùng vetted sources; `replenish_review()` có mode `agentic` hoặc `deterministic`. `review_from_evidence()` đối chiếu SKU và stock arithmetic.
- `retailiq/skills/__init__.py`: allowlist và nạp skill theo nhu cầu.
- `retailiq/domain/workflow_demo.py`: các scenario `week1…week4` lưu event giả lập có tính xác định để UI trình bày; **không phải** năm agent tự trị hay A2A thực tế.

### Một yêu cầu có gọi LLM bao nhiêu lần?

**Không có hằng số "một lần".** Offline path có thể trả lời không gọi LLM; full-mode có thể gồm bước routing, model-directed supervisor hoặc sinh câu trả lời RAG, tùy intent và config. Các SQL read và deterministic verification không cần LLM. **Đếm số lần thực tế bằng trace theo request**, không suy ra từ số node trên sơ đồ.

## Trade-offs và failure modes

1. **More agents ≠ more correctness**: nếu Sales chọn SKU A nhưng Inventory trả SKU B thì fail verification. Không cho supervisor tự bịa số để "hoàn thành".
2. **Follow-up scope**: lưu period, SKU, rank, location từ ngữ cảnh hợp lệ; từ chỉ định mơ hồ thì hỏi lại, không âm thầm chuyển sang tổng doanh thu cửa hàng.
3. **State/checkpoint**: lưu trạng thái cho continuation nhưng cần isolation và bounded context; checkpoint không là authenticated identity.
4. **Retry**: chỉ retry transient failure của read-only/idempotent operation; không dùng retry để lặp business mutation nhạy cảm.

## VERIFY / khi nào cần thiết kế lại

- Kiểm tra exact SKU/period/rank và negative scenarios ở [Testing](../27_BEHAVIORAL_ACCEPTANCE_MATRIX.md).
- Khi muốn chứng minh handoff, cần trace `Command`/actual node execution cùng request ID; không dùng screenshot graph làm bằng chứng.
- Chỉ thêm agent khi một subtask cần tool/permission/context/evaluation khác thực sự, và có scenario đo được lợi ích so với single-agent/function.

**Official reading (đối chiếu 2026-10-31):**
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangChain multi-agent choices](https://docs.langchain.com/oss/python/langchain/multi-agent)
- [Subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents) và [Handoffs](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs)

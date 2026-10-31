# MCP integration: vì sao có protocol nếu đã gọi SQL được?

**Problem:** backend RetailIQ đã có `inventory()` và SQL order lookup. Vậy thêm MCP để làm gì? **Không phải để làm stock chính xác hơn**; MCP giúp mô tả tool/resource ở một giao diện chuẩn mà client khác có thể khám phá và gọi. Khi ứng dụng vẫn chạy trong **một process, một database local**, direct Python call thường đơn giản hơn.

## Concepts: Tools, Resources, Prompts, Transport

- **Tool**: server công bố tên, schema input và khả năng thực thi (ví dụ: `inventory_lookup(sku)`). Tool invocation có thể trả dữ liệu hoặc lỗi; client phải kiểm tra schema/giá trị chứ không tin mù quáng.
- **Resource**: tài liệu/context địa chỉ bằng URI (ví dụ: `retailiq://semantics`). Nó **không phải** một lệnh cập nhật dữ liệu.
- **Prompt**: template prompt do server có thể công bố; **RetailIQ MCP server hiện không định nghĩa prompt primitive**.
- **Transport**: cách client/server chuyển thông điệp. `stdio` chạy server như subprocess local, dùng stdin/stdout. Streamable HTTP dùng khi cần endpoint/network độc lập — nhưng kéo theo auth, hosting, threat model và operational cost.

**MCP** chuẩn hóa biên kết nối; nó không tự tạo quyền truy cập, tính realtime, chính sách an ninh hoặc agent tự trị.

## Alternatives và quyết định

| Phương án | Khi đáng dùng | RetailIQ |
|---|---|---|
| Gọi `domain.analytics.inventory()` trực tiếp | Cùng process, cùng trust boundary, test đơn giản | **Default** cho nhiều đường SQL |
| HTTP API tự thiết kế | Có client remote cụ thể và contract cần kiểm soát | FastAPI là UI/backend boundary; không thay thế MCP stdio |
| MCP stdio | Muốn chứng minh tool discovery/invocation đúng protocol mà không deploy thêm server | **Đã implement local** với inventory/order read-only |
| Hosted MCP / Streamable HTTP | Nhiều client/network và hệ thống có identity/auth/operations | **Chưa triển khai**, không thêm chỉ vì xu hướng |

Điều kiện chọn MCP là **interoperability có ích**, không phải "mỗi domain tool phải là một MCP server".

## HOW — đường thực thi thật

- `retailiq/mcp_server.py`: `FastMCP` export tools `inventory_lookup`, `order_lookup` và resource `retailiq://semantics`; khởi chạy bằng `python -m retailiq.mcp_server` với **stdio**.
- `retailiq/mcp_adapter.py`: client spawn subprocess, gọi tool, parse và kiểm tra stock evidence bằng validator có sẵn.
- `retailiq/orchestration/agents.py` và `assistant.py`: dùng `RETAILIQ_INVENTORY_USE_MCP` để opt-in stock tool; không coi đó là real external WMS.
- `retailiq/api/workflows.py`: `RETAILIQ_WORKFLOW_USE_MCP=1` có thể thực hiện local MCP inventory read và so sánh với reviewed SQL. Các nguồn còn thiếu timestamp không trở thành fresh nhờ transport này.
- `retailiq/domain/semantic.py`: định nghĩa nghiệp vụ chung cho SQL/MCP; transport không được phép đổi ý nghĩa `available_stock`.

## Version / security warning

Tài liệu MCP đã có specification revision **2026-07-28** (với thay đổi protocol lifecycle so với các phiên bản handshake cũ). **Không giả định** dependency `mcp>=1.28,<2` và `langchain-mcp-adapters>=0.1,<1` trong các file requirements tự động tương thích mọi revision mới. Trước khi nâng cấp: xem **version đã cài thật**, protocol negotiated, output schema và integration tests. Đây là khuyến nghị kiểm tra, không phải báo lỗi đã xác nhận.

`stdio` subprocess local không phải authentication. Không để server đọc credential không cần thiết, không cho tool business mutation khi thiếu quyền, không đưa raw tool output vào prompt như chỉ thị đáng tin. Ngoài localhost phải thiết kế authorization riêng; không thêm hosted MCP vào dự án chỉ để minh họa.

## VERIFY / khi nào revisit

- Chạy `python -m scripts.smoke_mcp_stdio` trong môi trường có MCP deps: verify kết nối, list/call thực tế, đọc `inventory_lookup` và `order_lookup`, invalid SKU/order và compare SQL.
- Phân biệt `local_mcp_stdio` với `offline_sqlite`, `provider_backed` và một source live có timestamp đáng tin.
- Chỉ migrate sang remote MCP khi có nhu cầu external client cụ thể, contract auth, threat model và CI integration cho protocol version được chọn.

**Official reading (đối chiếu 2026-10-31):**
- [MCP specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [Tools primitive](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [Stdio / transports (2025-11-25, legacy handshake reference)](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Legacy vs modern protocol negotiation (SDK docs)](https://ts.sdk.modelcontextprotocol.io/v2/protocol-versions)

"""Read-only Inventory MCP stdio adapter, opt-in for the local Week 2 demo."""
import asyncio
import json
import sys

from retailiq.domain.analytics import _validate_inventory
from retailiq.observability import observed


def decode_tool_result(value) -> dict:
    """Normalize MCP/LangChain versions without accepting ambiguous tool outputs.

    LangChain's direct tool.ainvoke may return a dict, a JSON string, text
    content blocks, or a ToolMessage with content/artifact. Validate the
    business schema *after* decoding; never manufacture a successful record.
    """
    if isinstance(value, dict):
        if "records" in value or "order" in value:
            return value
        for key in ("structuredContent", "structured_content", "content"):
            if key in value:
                return decode_tool_result(value[key])
        raise ValueError("MCP result has no recognized structured payload")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError) as error:
            raise ValueError("MCP text is not valid JSON") from error
        return decode_tool_result(parsed)
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError("MCP returned an ambiguous number of content blocks")
        item = value[0]
        if isinstance(item, dict) and item.get("type") == "text":
            return decode_tool_result(item.get("text"))
        if hasattr(item, "text"):
            return decode_tool_result(item.text)
        return decode_tool_result(item)
    if hasattr(value, "artifact") and getattr(value, "artifact") is not None:
        artifact = value.artifact
        try:
            return decode_tool_result(artifact)
        except ValueError:
            pass  # ToolMessage may carry raw content in .content instead.
    if hasattr(value, "content"):
        return decode_tool_result(value.content)
    raise ValueError("Unsupported MCP result: " + type(value).__name__)


async def _read(sku: str) -> list[dict]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({
        "retailiq": {"command": sys.executable,
                     "args": ["-m", "retailiq.mcp_server"],
                     "transport": "stdio"}
    })
    tools = await client.get_tools()
    tool = next((tool for tool in tools if tool.name == "inventory_lookup"), None)
    if tool is None:
        raise RuntimeError("Inventory MCP tool missing")
    # The span surrounds a real MCP stdio tool call plus validation, not
    # discovery or the mere presence of an MCP server in configuration.
    with observed('mcp.tool', agent='inventory_agent', tool='inventory_lookup',
                  mcp_server='retailiq', execution_mode='full'):
        response = decode_tool_result(await tool.ainvoke({"sku": sku}))
        if not isinstance(response.get("records"), list):
            raise ValueError("Unexpected inventory MCP record schema")
        return _validate_inventory(response["records"], sku)


def read_inventory(sku: str) -> list[dict]:
    # FastAPI invokes this in a sync worker, not inside an existing event loop.
    return asyncio.run(_read(sku))

"""Optional LangChain MCP adapter, enabled only by RETAILIQ_WORKFLOW_USE_MCP=1."""
import asyncio
import json
import sys

from retailiq.domain.analytics import _validate_inventory


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
    response = await tool.ainvoke({"sku": sku})
    if isinstance(response, str):
        response = json.loads(response)
    if not isinstance(response, dict) or not isinstance(response.get("records"), list):
        raise ValueError("Unexpected inventory MCP response")
    return _validate_inventory(response["records"], sku)


def read_inventory(sku: str) -> list[dict]:
    # FastAPI invokes this in a sync worker, not inside an existing event loop.
    return asyncio.run(_read(sku))

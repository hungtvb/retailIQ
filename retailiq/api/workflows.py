"""Local workflow graph demo API; no real authentication or business mutations."""
from fastapi import APIRouter, HTTPException
import os
from pydantic import BaseModel, Field
from typing import Literal
from retailiq.domain.workflow_demo import definitions, run_demo, read_run, review_run
from retailiq.domain.semantic import contracts
from retailiq.domain.freshness_routing import route_freshness

router = APIRouter(prefix="/api/workflows", tags=["workflow-demo"])


class RunInput(BaseModel):
    scenario: Literal["week1", "week2", "week3", "alerts", "week4"]
    sku: str = Field(default="EL-003", min_length=3, max_length=64)
    quantity: int = Field(default=1, ge=1, le=20)
    role: Literal["analyst", "manager"] = "analyst"


class ReviewInput(BaseModel):
    role: Literal["analyst", "manager"]
    decision: Literal["approve", "reject"]


class FreshnessRouteInput(BaseModel):
    """Explicit metric contract: never guess a source from loose keyword text."""
    metric: Literal["available_stock", "net_revenue", "top_sellers",
                    "product_knowledge", "order_state"]
    requested_tier: Literal["live", "15_min", "hourly", "daily"] | None = None
    sku: str | None = Field(default=None, max_length=64)


@router.post("/freshness/route")
def freshness_route(data: FreshnessRouteInput):
    """Select a source and verify actual data timestamps where available.

    For non-inventory sources the synthetic database has no trustworthy
    refresh timestamp, so routing is visible but freshness is UNVERIFIED.
    """
    if data.metric != "available_stock" and data.sku is not None:
        raise HTTPException(status_code=422,
                            detail="SKU filter applies only to inventory freshness")
    if data.metric == "available_stock" and not data.sku:
        raise HTTPException(status_code=422, detail="Inventory freshness requires a SKU")
    use_mcp = os.getenv("RETAILIQ_WORKFLOW_USE_MCP", "0") == "1"
    try:
        if data.metric == "available_stock":
            from retailiq.domain.analytics import inventory
            rows = inventory(data.sku)
            if use_mcp:
                from retailiq.mcp_adapter import read_inventory
                mcp_rows = read_inventory(data.sku)
                if mcp_rows != rows:
                    raise ValueError("MCP inventory differs from reviewed SQL")
                rows = mcp_rows
            route = route_freshness(data.metric, requested_tier=data.requested_tier,
                                    inventory_rows=rows, use_mcp=use_mcp)
            return {**route, "tool_execution": "executed_readonly",
                    "execution_mode": "local_mcp_stdio" if use_mcp else "local_sqlite"}
        route = route_freshness(data.metric, requested_tier=data.requested_tier)
        return {**route, "execution_mode": "route_only_no_source_timestamp"}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except Exception as error:
        from retailiq.observability import log_exception
        log_exception("workflow.freshness_failed", error)
        raise HTTPException(status_code=503, detail="Freshness source unavailable") from None


@router.get("/definitions")
def get_definitions():
    return {"scenarios": definitions(), "scope": "synthetic_local_simulation",
            "role_notice": "Role picker is a teaching aid, not authentication or real RBAC."}


@router.get("/semantics")
def get_semantics():
    return contracts()


@router.post("/run")
def create_run(data: RunInput):
    try:
        return run_demo(data.scenario, data.sku, data.quantity, data.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:
        from retailiq.observability import log_exception
        log_exception("workflow.demo_failed", exc)
        raise HTTPException(status_code=503, detail="Workflow data unavailable") from None


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    item = read_run(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return item


@router.post("/runs/{run_id}/review")
def manager_review(run_id: str, data: ReviewInput):
    try:
        return review_run(run_id, data.role, data.decision)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow not found") from None
    except PermissionError:
        raise HTTPException(status_code=403, detail="Simulated manager role required") from None
    except ValueError:
        raise HTTPException(status_code=409, detail="Workflow is not awaiting review") from None

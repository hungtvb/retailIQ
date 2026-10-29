"""Local workflow graph demo API; no real authentication or business mutations."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from retailiq.domain.workflow_demo import definitions, run_demo, read_run, review_run

router = APIRouter(prefix="/api/workflows", tags=["workflow-demo"])


class RunInput(BaseModel):
    scenario: Literal["week2", "week3", "alerts", "week4"]
    sku: str = Field(default="EL-003", min_length=3, max_length=64)
    quantity: int = Field(default=1, ge=1, le=20)
    role: Literal["analyst", "manager"] = "analyst"


class ReviewInput(BaseModel):
    role: Literal["analyst", "manager"]
    decision: Literal["approve", "reject"]


@router.get("/definitions")
def get_definitions():
    return {"scenarios": definitions(), "scope": "synthetic_local_simulation",
            "role_notice": "Role picker is a teaching aid, not authentication or real RBAC."}


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

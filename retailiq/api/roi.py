"""Stateless Cost & ROI dashboard endpoints (no secrets, no persisted values)."""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from retailiq.domain.economics import ROIInputs, build_report

router = APIRouter(prefix='/api/roi', tags=['cost-roi'])


class ROIForm(BaseModel):
    monthly_questions: int = Field(default=1000, ge=0, le=10_000_000)
    assisted_share: float = Field(default=0.60, ge=0, le=1)
    minutes_saved: float = Field(default=4, ge=0, le=1440)
    labor_cost_per_hour_vnd: float = Field(default=150_000, ge=0, le=1_000_000_000)
    monthly_operating_cost_vnd: float = Field(default=1_200_000, ge=0, le=10_000_000_000_000)
    build_cost_vnd: float = Field(default=18_000_000, ge=0, le=10_000_000_000_000)
    avg_input_tokens: int = Field(default=800, ge=0, le=10_000_000)
    avg_output_tokens: int = Field(default=200, ge=0, le=10_000_000)
    input_usd_per_1m: float = Field(default=1, ge=0, le=100_000)
    output_usd_per_1m: float = Field(default=4, ge=0, le=100_000)
    monthly_embedding_tokens: int = Field(default=500_000, ge=0, le=10_000_000_000)
    embedding_usd_per_1m: float = Field(default=0.1, ge=0, le=100_000)


@router.get('/defaults')
def defaults():
    return ROIForm().model_dump()


@router.post('/estimate')
def estimate(data: ROIForm):
    roi = ROIInputs(
        monthly_questions=data.monthly_questions,
        assisted_share=data.assisted_share,
        minutes_saved=data.minutes_saved,
        labor_cost_per_hour_vnd=data.labor_cost_per_hour_vnd,
        monthly_operating_cost_vnd=data.monthly_operating_cost_vnd,
        build_cost_vnd=data.build_cost_vnd,
    )
    return build_report(
        roi,
        avg_input_tokens=data.avg_input_tokens,
        avg_output_tokens=data.avg_output_tokens,
        input_usd_per_1m=data.input_usd_per_1m,
        output_usd_per_1m=data.output_usd_per_1m,
        monthly_embedding_tokens=data.monthly_embedding_tokens,
        embedding_usd_per_1m=data.embedding_usd_per_1m,
    )

"""Pure, local-only financial modeling for the Week 1 demo.

No pricing feed, token telemetry, or business baseline is implied by this module.
All values are user-supplied illustrative assumptions.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ROIInputs:
    monthly_questions: int
    assisted_share: float
    minutes_saved: float
    labor_cost_per_hour_vnd: float
    monthly_operating_cost_vnd: float
    build_cost_vnd: float


def _bounded_number(name: str, value: object, maximum: float, *,
                    integer: bool = False) -> None:
    """Apply the same finite, non-boolean numeric limits as the local API."""
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            (integer and not isinstance(value, int))):
        raise ValueError(f'Invalid {name}')
    if not 0 <= value <= maximum or not math.isfinite(value):
        raise ValueError(f'Out-of-range {name}')


def _check_roi(s: ROIInputs) -> None:
    if not isinstance(s, ROIInputs):
        raise ValueError('Invalid ROI inputs')
    for name, limit, integer in (
        ('monthly_questions', 10_000_000, True),
        ('assisted_share', 1, False),
        ('minutes_saved', 1440, False),
        ('labor_cost_per_hour_vnd', 1_000_000_000, False),
        ('monthly_operating_cost_vnd', 10_000_000_000_000, False),
        ('build_cost_vnd', 10_000_000_000_000, False),
    ):
        _bounded_number(name, getattr(s, name), limit, integer=integer)


def evaluate(s: ROIInputs) -> dict:
    _check_roi(s)
    hours = s.monthly_questions * s.assisted_share * s.minutes_saved / 60
    gross = hours * s.labor_cost_per_hour_vnd
    net = gross - s.monthly_operating_cost_vnd
    return {
        'hours_saved_per_month': hours,
        'gross_monthly_benefit_vnd': gross,
        'monthly_net_benefit_vnd': net,
        'payback_months': s.build_cost_vnd / net if net > 0 else None,
    }


def llm_cost_usd(requests: int, avg_input_tokens: int, avg_output_tokens: int,
                 input_usd_per_1m: float, output_usd_per_1m: float,
                 monthly_embedding_tokens: int = 0,
                 embedding_usd_per_1m: float = 0.0) -> float:
    for name, value, limit, integer in (
        ('requests', requests, 10_000_000, True),
        ('avg_input_tokens', avg_input_tokens, 10_000_000, True),
        ('avg_output_tokens', avg_output_tokens, 10_000_000, True),
        ('input_usd_per_1m', input_usd_per_1m, 100_000, False),
        ('output_usd_per_1m', output_usd_per_1m, 100_000, False),
        ('monthly_embedding_tokens', monthly_embedding_tokens, 10_000_000_000, True),
        ('embedding_usd_per_1m', embedding_usd_per_1m, 100_000, False),
    ):
        _bounded_number(name, value, limit, integer=integer)
    return ((requests * avg_input_tokens * input_usd_per_1m)
            + (requests * avg_output_tokens * output_usd_per_1m)
            + monthly_embedding_tokens * embedding_usd_per_1m) / 1_000_000


def build_report(roi: ROIInputs, *, avg_input_tokens: int, avg_output_tokens: int,
                 input_usd_per_1m: float, output_usd_per_1m: float,
                 monthly_embedding_tokens: int, embedding_usd_per_1m: float) -> dict:
    """Compute a report; do not combine USD token forecast with all-in VND budget.

    monthly_operating_cost_vnd already includes the intended model spend.
    Converting USD to VND and subtracting it again would double-count it.
    """
    result = evaluate(roi)
    # Validate *all* token assumptions before any derived number is returned.
    token_total = llm_cost_usd(
        roi.monthly_questions, avg_input_tokens, avg_output_tokens,
        input_usd_per_1m, output_usd_per_1m,
        monthly_embedding_tokens, embedding_usd_per_1m)
    input_cost = roi.monthly_questions * avg_input_tokens * input_usd_per_1m / 1_000_000
    output_cost = roi.monthly_questions * avg_output_tokens * output_usd_per_1m / 1_000_000
    embedding_cost = monthly_embedding_tokens * embedding_usd_per_1m / 1_000_000
    sensitivity = []
    for share in (0.10, 0.30, 0.60):
        case = ROIInputs(
            roi.monthly_questions, share, roi.minutes_saved,
            roi.labor_cost_per_hour_vnd, roi.monthly_operating_cost_vnd,
            roi.build_cost_vnd)
        value = evaluate(case)
        sensitivity.append({'assisted_share': share, **value})
    annual_return = result['monthly_net_benefit_vnd'] * 12 - roi.build_cost_vnd
    return {
        'report_type': 'illustrative_estimate',
        'currency_for_business_case': 'VND',
        'business': {
            **result,
            'initial_build_cost_vnd': roi.build_cost_vnd,
            'operating_budget_all_in_vnd': roi.monthly_operating_cost_vnd,
            'year_one_net_roi_percent': (annual_return / roi.build_cost_vnd * 100
                                         if roi.build_cost_vnd > 0 else None),
        },
        'agent_cost_estimate': {
            'currency': 'USD',
            'llm_input_cost_usd': input_cost,
            'llm_output_cost_usd': output_cost,
            'embedding_cost_usd': embedding_cost,
            'monthly_token_cost_usd': token_total,
            'cost_per_request_usd': (token_total / roi.monthly_questions
                                     if roi.monthly_questions else None),
            'pricing_is_example_only': True,
        },
        'sensitivity': sensitivity,
        'assumptions': [
            'Synthetic retailer; no real business ROI or time savings have been measured.',
            'Token counts and USD unit prices are editable examples, not observed LangSmith telemetry or a provider quote.',
            'VND operating budget is all-in; USD token forecast is informational and is not subtracted a second time.',
            'The simple payback model assumes monthly benefit remains constant.'
        ],
    }

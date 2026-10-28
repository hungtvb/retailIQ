"""Cost/ROI failure-mode regression: every value is an illustrative assumption."""
import math

import pytest
from fastapi.testclient import TestClient

from retailiq.api import app
from retailiq.domain.economics import ROIInputs, build_report, evaluate, llm_cost_usd


BASE = ROIInputs(1000, .6, 4, 150_000, 1_200_000, 18_000_000)


@pytest.mark.parametrize('attribute,value', [
    ('monthly_questions', True),
    ('monthly_questions', 0.5),
    ('monthly_questions', -1),
    ('assisted_share', float('nan')),
    ('assisted_share', float('inf')),
    ('assisted_share', 1.01),
    ('minutes_saved', '4'),
    ('labor_cost_per_hour_vnd', float('nan')),
    ('monthly_operating_cost_vnd', float('-inf')),
    ('build_cost_vnd', 10_000_000_000_001),
])
def test_roi_domain_fails_closed_on_invalid_numbers(attribute, value):
    values = vars(BASE).copy()
    values[attribute] = value
    with pytest.raises(ValueError):
        evaluate(ROIInputs(**values))


@pytest.mark.parametrize('change', [
    {'requests': True},
    {'avg_input_tokens': 0.5},
    {'avg_output_tokens': -1},
    {'input_usd_per_1m': float('nan')},
    {'output_usd_per_1m': float('inf')},
    {'monthly_embedding_tokens': 10_000_000_001},
    {'embedding_usd_per_1m': float('nan')},
])
def test_token_cost_rejects_invalid_assumptions(change):
    values = dict(requests=1000, avg_input_tokens=700, avg_output_tokens=180,
                  input_usd_per_1m=1.0, output_usd_per_1m=4.0,
                  monthly_embedding_tokens=500000, embedding_usd_per_1m=.1)
    values.update(change)
    with pytest.raises(ValueError):
        llm_cost_usd(**values)


def test_cost_report_rejects_invalid_token_inputs_without_partial_results():
    with pytest.raises(ValueError):
        build_report(BASE, avg_input_tokens=800, avg_output_tokens=200,
                     input_usd_per_1m=float('nan'), output_usd_per_1m=4,
                     monthly_embedding_tokens=500000, embedding_usd_per_1m=.1)


def test_zero_workload_and_zero_build_have_explicit_nonfiction_semantics():
    roi = ROIInputs(0, 0, 4, 150000, 100000, 0)
    report = build_report(
        roi, avg_input_tokens=800, avg_output_tokens=200,
        input_usd_per_1m=1, output_usd_per_1m=4,
        monthly_embedding_tokens=0, embedding_usd_per_1m=0)
    assert report['report_type'] == 'illustrative_estimate'
    assert report['business']['monthly_net_benefit_vnd'] == -100000
    assert report['business']['payback_months'] is None
    assert report['business']['year_one_net_roi_percent'] is None
    assert report['agent_cost_estimate']['cost_per_request_usd'] is None
    assert report['agent_cost_estimate']['monthly_token_cost_usd'] == 0


def test_roi_api_rejects_nonfinite_json_numbers():
    client = TestClient(app)
    for key in ('assisted_share', 'input_usd_per_1m', 'minutes_saved'):
        response = client.post('/api/roi/estimate', content=
                               '{"' + key + '": "NaN"}',
                               headers={'Content-Type': 'application/json'})
        assert response.status_code == 422


def test_large_valid_inputs_still_return_json_finite_values():
    roi = ROIInputs(10_000_000, 1, 1440, 1_000_000_000,
                    10_000_000_000_000, 10_000_000_000_000)
    result = evaluate(roi)
    assert all(value is None or math.isfinite(value) for value in result.values())

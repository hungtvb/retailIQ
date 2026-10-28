"""Cost & ROI API/UI regression tests, without provider credentials."""
from fastapi.testclient import TestClient
from retailiq.api import app

client = TestClient(app)


def test_roi_dashboard_present_on_ui():
    response = client.get('/')
    assert response.status_code == 200
    html = response.text
    assert 'Cost &amp; ROI' in html
    assert 'roi-panel' in html
    assert '/api/roi/estimate' in client.get('/assets/app.js').text
    assert 'illustrative' in html.lower()


def test_roi_defaults_are_safe_and_no_keys():
    response = client.get('/api/roi/defaults')
    assert response.status_code == 200
    payload = response.json()
    assert payload['monthly_questions'] == 1000
    assert payload['assisted_share'] == .6
    assert all('key' not in name.lower() for name in payload)


def test_roi_estimate_matches_business_case():
    response = client.post('/api/roi/estimate', json={})
    assert response.status_code == 200
    data = response.json()
    assert data['report_type'] == 'illustrative_estimate'
    assert data['business']['gross_monthly_benefit_vnd'] == 6_000_000
    assert data['business']['monthly_net_benefit_vnd'] == 4_800_000
    assert data['business']['payback_months'] == 3.75
    assert data['agent_cost_estimate']['monthly_token_cost_usd'] == 1.65
    assert len(data['sensitivity']) == 3
    assert data['sensitivity'][0]['payback_months'] is None
    assert 'actual' not in data['report_type']


def test_roi_calculation_responds_to_form_changes():
    data = client.post('/api/roi/estimate', json={
        'assisted_share': 0.3,
        'avg_input_tokens': 2000,
        'monthly_questions': 2000,
    }).json()
    assert data['business']['payback_months'] == 3.75
    assert data['agent_cost_estimate']['llm_input_cost_usd'] == 4.0


def test_roi_no_payback_when_net_is_negative():
    response = client.post('/api/roi/estimate', json={
        'assisted_share': 0.1,
        'monthly_operating_cost_vnd': 9_000_000,
    })
    assert response.status_code == 200
    assert response.json()['business']['payback_months'] is None


def test_roi_input_validation():
    for payload in ({'assisted_share': 1.1}, {'monthly_questions': -1},
                    {'input_usd_per_1m': -0.5}):
        response = client.post('/api/roi/estimate', json=payload)
        assert response.status_code == 422


def test_roi_api_does_not_return_provider_credentials(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'secret-should-not-appear')
    response = client.post('/api/roi/estimate', json={})
    assert response.status_code == 200
    assert 'secret-should-not-appear' not in response.text

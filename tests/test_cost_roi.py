from scripts.cost_roi import ROIInputs,evaluate,llm_cost_usd
import pytest

def test_illustrative_payback():
    r=evaluate(ROIInputs(1000,.6,4,150000,1200000,18000000))
    assert r['hours_saved_per_month']==40
    assert r['gross_monthly_benefit_vnd']==6_000_000
    assert r['monthly_net_benefit_vnd']==4_800_000
    assert r['payback_months']==3.75

def test_no_payback():
    r=evaluate(ROIInputs(10,.1,1,100000,1000000,5000000))
    assert r['payback_months'] is None

def test_token_cost_calculation():
    result=llm_cost_usd(1000,700,180,1.0,4.0,500000,0.1)
    assert result==pytest.approx(.7+.72+.05)

def test_invalid_inputs():
    with pytest.raises(ValueError):evaluate(ROIInputs(-1,.5,5,100000,1,1))

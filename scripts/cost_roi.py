"""CLI compatibility entrypoint; calculations live in retailiq.domain.economics."""
from retailiq.domain.economics import ROIInputs, evaluate, llm_cost_usd, build_report

if __name__ == '__main__':
    scenario = ROIInputs(1000, 0.6, 4, 150000, 1200000, 18000000)
    result = evaluate(scenario)
    print('ILLUSTRATIVE ONLY — not a measured RetailIQ benefit or provider price')
    for key, value in result.items():
        print(f'{key}: {value:,.2f}' if value is not None else f'{key}: no payback')

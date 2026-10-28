"""Strict live integration gate; no offline or mocked evidence accepted."""
import json
import os
from pathlib import Path
from uuid import uuid4
from retailiq.assistant import ask
from retailiq.core.config import safe_status
from retailiq.observability import bind_context

CASES = [
    ('How many units of AlphaBook Pro 14 are currently in stock?', 'stock'),
    ('What is the revenue this month?', 'revenue'),
    ('Which products are top sellers?', 'top'),
    ('Tell me about USB-C GaN Charger 65W', 'product'),
    ('Which top seller needs a replenishment review based on stock?', 'decision'),
]

def main():
    if os.getenv('RETAILIQ_MODE') != 'full':
        raise RuntimeError('RETAILIQ_MODE=full required; offline does not count')
    if not safe_status()['provider_ready']:
        raise RuntimeError('Configure real provider credentials first')
    outcomes = []
    for question, wanted in CASES:
        with bind_context(request=uuid4().hex, session=''):
            try:
                result = ask(question)
                assert result['intent'] == wanted, 'Wrong intent'
                assert result['mode'].startswith('LangGraph'), 'Not full LangGraph'
                if wanted == 'product':
                    assert result['contexts'], 'No vector contexts retrieved'
                    assert 'could not verify' not in result['answer'].lower()
                if wanted == 'decision':
                    assert len(result.get('subagents', [])) >= 2
                outcomes.append({'intent': wanted, 'status': 'PASS',
                                 'sql_rows': len(result.get('records', [])),
                                 'retrieved_sources': list(dict.fromkeys(
                                     c['source'] for c in result.get('contexts', [])))})
            except Exception as error:
                outcomes.append({'intent': wanted, 'status': 'FAIL',
                                 'error_type': type(error).__name__})
    report = {'mode': 'full', 'checks': outcomes,
              'all_passed': all(x['status'] == 'PASS' for x in outcomes),
              'langsmith_remote_trace_verified': False,
              'ragas_scores_verified': False}
    path = Path(__file__).resolve().parents[1] / 'data' / 'full_e2e_report.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not report['all_passed']:
        raise SystemExit(1)

if __name__ == '__main__':
    main()

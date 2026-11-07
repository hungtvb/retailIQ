"""Offline evidence gates: the retrieval audit and evaluation must discriminate.

No provider calls: the audit check is exercised with fixed response payloads
and the evaluation with a fake search callable.
"""
from __future__ import annotations

from pathlib import Path

from scripts import eval_retrieval
from scripts.audit_queries import Case, assess

ROOT = Path(__file__).resolve().parents[1]


def _first_heading(source: str) -> str:
    """First Markdown H1 of a document, or '' when the format has no heading."""
    text = (ROOT / source).read_text(encoding='utf-8', errors='replace')
    for line in text.splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return ''


def test_audit_rejects_wrong_source():
    case = Case('RAG-01', 'product', ('Thông số sạc 65W?',), 'product_sources',
                'LIKELY_PASS', 'retrieval/grounding', 'Document-backed answer',
                expected_source='data/product_docs/EL-003.md')
    wrong = {'intent': 'product', 'answer': 'unrelated nonsense',
             'contexts': [{'source': 'data/product_docs/EL-001.md'}]}
    right = {'intent': 'product', 'answer': 'PD 3.0 up to 65W single port',
             'contexts': [{'source': 'data/knowledge/help_articles.json'},
                          {'source': 'data/product_docs/EL-003.md'}]}
    assert assess(case, wrong, None)[0] is False
    assert assess(case, right, None)[0] is True


def test_eval_query_set_has_no_title_leakage():
    leaked = []
    for case_id, question, expected_source in eval_retrieval.CASES:
        if not expected_source:
            continue
        heading = _first_heading(expected_source)
        if heading and heading.casefold() in question.casefold():
            leaked.append(case_id)
    assert leaked == [], f'queries leak the expected document title: {leaked}'


def test_eval_has_distractors_and_abstention():
    expected = [source for _, _, source in eval_retrieval.CASES if source]
    assert len(eval_retrieval.CASES) >= 12
    assert len(set(expected)) >= 3
    assert sum(1 for source in expected if source.startswith('data/knowledge/')) >= 2
    assert any(source is None for _, _, source in eval_retrieval.CASES)
    assert eval_retrieval.DATASET.endswith('v2')


def test_abstention_scores_only_on_empty_context():
    abstain = (('X', 'What is our current stock level in the Hanoi warehouse?', None),)
    empty = eval_retrieval.evaluate_source_retrieval(abstain, lambda q, k: [], k=3)
    assert empty['summary']['source_recall_at_k'] == 1.0
    assert empty['summary']['mrr'] == 1.0
    answered = eval_retrieval.evaluate_source_retrieval(
        abstain, lambda q, k: [{'source': 'data/product_docs/EL-001.md'}], k=3)
    assert answered['summary']['source_recall_at_k'] == 0.0
    assert answered['summary']['mrr'] == 0.0

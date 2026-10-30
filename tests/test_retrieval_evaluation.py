"""Pure source-level retrieval metric tests; no embedding/provider credentials."""
import json
import pytest

from scripts import eval_retrieval as evaluation


def test_recall_mrr_per_source_and_nonmatched_queries():
    cases = (
        ('A', 'charger specifications', 'a.md'),
        ('B', 'second product', 'b.md'),
        ('C', 'missing source', 'c.md'),
    )
    answers = {
        'charger specifications': [{'source':'a.md'}, {'source':'z.md'}],
        'second product': [{'source':'x.md'}, {'source':'b.md'}],
        'missing source': [{'source':'other.md'}],
    }
    report = evaluation.evaluate_source_retrieval(
        cases, lambda q, k: answers[q][:k], k=3)
    assert report['summary']['questions'] == 3
    assert report['summary']['source_recall_at_k'] == 0.6667
    assert report['summary']['mrr'] == 0.5
    assert report['per_source']['a.md']['mrr'] == 1.0
    assert report['per_source']['b.md']['mrr'] == 0.5
    assert report['per_source']['c.md']['source_recall_at_k'] == 0.0
    assert all(row['latency_ms'] >= 0 for row in report['cases'])


def test_provider_failure_does_not_produce_partial_success(tmp_path):
    report_file = tmp_path / 'retrieval.json'
    def fails(_question, _k):
        raise TimeoutError('Embedding provider timeout')
    with pytest.raises(TimeoutError):
        report = evaluation.evaluate_source_retrieval(
            (('A', 'example', 'a.md'),), fails)
        evaluation.save_atomic(report_file, report)
    assert not report_file.exists()


def test_report_write_is_atomic_and_reloads(tmp_path):
    target = tmp_path / 'reports' / 'retrieval.json'
    sample = {'evaluation_mode': 'unit_only', 'strategies': {}}
    evaluation.save_atomic(target, sample)
    assert json.loads(target.read_text()) == sample
    assert not list(target.parent.glob('*.tmp'))


def test_live_cli_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr('sys.argv', ['eval_retrieval'])
    with pytest.raises(SystemExit) as error:
        evaluation.main()
    assert error.value.code == 2

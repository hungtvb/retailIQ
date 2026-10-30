"""W2 source reliability report: metrics must come from validated evidence."""
from __future__ import annotations

import json
import pytest

from scripts.report_source_reliability import build_reliability_report, main


def fixture():
    queries = {
        'mode': 'offline',
        'summary': {'pass': 2, 'fail': 1, 'error': 0},
        'results': [
            {'id': 'S1', 'group': 'sales', 'status': 'PASS'},
            {'id': 'S2', 'group': 'cross_domain', 'status': 'FAIL'},
            {'id': 'S3', 'group': 'product', 'status': 'PASS'},
        ],
    }
    workflow = {
        'mode': 'offline_synthetic',
        'summary': {'pass': 1, 'fail': 0, 'total': 1},
        'results': [{'id': 'W2', 'status': 'PASS'}],
    }
    edges = {
        'mode': 'offline_synthetic',
        'summary': {'pass': 1, 'fail': 0, 'total': 1},
        'results': [{'id': 'E2', 'status': 'PASS'}],
    }
    return queries, workflow, edges


def test_source_aggregation_exposes_failures_and_does_not_invent_provider_scores():
    report = build_reliability_report(*fixture())
    assert report['sources']['orders']['cases'] == 2
    assert report['sources']['orders']['pass_fraction'] == 0.5
    assert report['sources']['inventory']['fail'] == 1
    assert report['sources']['product_knowledge']['pass'] == 1
    assert report['retrieval']['status'] == 'NOT_MEASURED'
    assert report['freshness']['status'] == 'TARGETS_ONLY_NOT_LIVE_VERIFIED'
    assert report['mcp']['status'] == 'NOT_ASSERTED_FROM_THESE_REPORTS'


def test_invalid_summary_and_unknown_group_fail_closed():
    reports = list(fixture())
    reports[0]['summary']['fail'] = 0
    with pytest.raises(ValueError, match='summary differs'):
        build_reliability_report(*reports)
    reports = list(fixture())
    reports[0]['results'][0]['group'] = 'pretend_live'
    with pytest.raises(ValueError, match='Unknown'):
        build_reliability_report(*reports)


def test_fake_retrieval_report_is_rejected():
    with pytest.raises(ValueError, match='real provider'):
        build_reliability_report(*fixture(), retrieval={
            'evaluation_mode': 'fake_embedding', 'strategies': {},
        })


def test_cli_strict_returns_nonzero_and_writes_truthful_report(tmp_path, monkeypatch):
    paths = []
    for name, data in zip(('queries', 'workflows', 'edges'), fixture()):
        p = tmp_path / (name + '.json')
        p.write_text(json.dumps(data), encoding='utf-8')
        paths += [str(p)]
    out = tmp_path / 'source_reliability.json'
    monkeypatch.setattr('sys.argv', [
        'report_source_reliability', '--queries', paths[0],
        '--workflows', paths[1], '--edges', paths[2], '--out', str(out),
        '--strict',
    ])
    assert main() == 1
    result = json.loads(out.read_text(encoding='utf-8'))
    assert result['test_suites']['business_queries']['fail'] == 1
    assert result['retrieval']['status'] == 'NOT_MEASURED'


def test_aggregates_freshness_policy_fixtures_separately_from_live_sla():
    sample = {
        "mode": "offline_synthetic",
        "summary": {"pass": 2, "fail": 1, "total": 3},
        "results": [
            {"id": "FR-1", "source": "inventory", "status": "PASS"},
            {"id": "FR-2", "source": "inventory", "status": "PASS"},
            {"id": "FR-3", "source": "orders", "status": "FAIL"},
        ],
    }
    report = build_reliability_report(*fixture(), freshness=sample)
    freshness = report["freshness"]
    assert freshness["status"] == "LOCAL_FIXTURE_POLICY_CHECKED"
    assert freshness["scenarios"]["pass"] == 2
    assert freshness["by_source"]["inventory"]["cases"] == 2
    assert freshness["by_source"]["orders"]["fail"] == 1
    assert freshness["production_sla_guaranteed"] is False
    assert report["test_suites"]["freshness_policy"]["fail"] == 1


def test_freshness_report_cannot_claim_unverified_live_evidence():
    forged = {
        "mode": "provider_live",
        "summary": {"pass": 1, "fail": 0, "total": 1},
        "results": [{"id": "FR-1", "source": "inventory", "status": "PASS"}],
    }
    with pytest.raises(ValueError, match="offline synthetic"):
        build_reliability_report(*fixture(), freshness=forged)
    forged["mode"] = "offline_synthetic"
    forged["results"][0]["source"] = "invented_source"
    with pytest.raises(ValueError, match="Unrecognized freshness audit source"):
        build_reliability_report(*fixture(), freshness=forged)

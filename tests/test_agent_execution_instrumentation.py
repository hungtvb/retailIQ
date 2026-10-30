"""Execution instrumentation integration: real delegated LangGraph subgraphs, not fixtures."""
from datetime import date
import pytest

from scripts.seed import seed
from retailiq.observability import bind_context, bind_event_sink
from retailiq.skills import load_skill


def test_real_delegated_subagents_have_observed_spans(tmp_path, monkeypatch):
    pytest.importorskip('langgraph')
    db = tmp_path / 'retail.sqlite3'
    seed(db, write_support_files=False, reference_date=date(2026, 10, 28))
    monkeypatch.setenv('RETAILIQ_DATA_DB', str(db))
    monkeypatch.setenv('RETAILIQ_AS_OF', '2026-10-28')
    monkeypatch.setenv('RETAILIQ_SUPERVISOR_MODE', 'deterministic')
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'trace.jsonl'))
    from retailiq.orchestration.agents import replenish_review

    events = []
    with bind_context(request='agent-test-request', session='agent-test-session'), bind_event_sink(events.append):
        result = replenish_review()

    assert result['subagents'] == ['sales_agent', 'inventory_agent']
    assert result['records'] and result['answer']
    starts = [x for x in events if x['event'] == 'agent.subagent.started']
    completes = [x for x in events if x['event'] == 'agent.subagent.completed']
    assert [x['subagent'] for x in starts] == ['sales_agent', 'inventory_agent']
    assert [x['subagent'] for x in completes] == ['sales_agent', 'inventory_agent']
    assert all(e['agent'] == 'retail_supervisor' and e['execution_mode'] == 'full'
               and e['request_id'] == 'agent-test-request' for e in starts + completes)
    assert all(e['duration_ms'] >= 0 for e in completes)
    # SQL tools execute inside the subagent graph, not at supervisor level.
    assert any(e['event'] == 'tool.sql.completed' and e['agent'] == 'sales_agent'
               for e in events)
    assert any(e['event'] == 'tool.sql.completed' and e['agent'] == 'inventory_agent'
               for e in events)
    # A selected skill was not necessarily loaded or read in deterministic mode.
    assert not any(e['event'] == 'skill.loaded' for e in events)


def test_skill_loaded_has_explicit_agent_without_leaking_content(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'skill.jsonl'))
    events = []
    with bind_context(request='skill-test'), bind_event_sink(events.append):
        content = load_skill('product_grounding', agent='product_agent')
    assert 'product' in content.casefold()
    loads = [e for e in events if e['event'] == 'skill.loaded']
    assert len(loads) == 1
    assert loads[0]['agent'] == 'product_agent'
    assert loads[0]['skill'] == 'product_grounding'
    assert 'content' not in loads[0] and 'prompt' not in loads[0]

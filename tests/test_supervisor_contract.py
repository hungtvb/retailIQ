"""Supervisor delegation contract: never trust a model-selected SKU or task order."""
from __future__ import annotations

import sys
from types import ModuleType

import pytest

from retailiq.orchestration import agentic_supervisor


def _run(monkeypatch, execute, *, sales_records=None, stock_records=None):
    """Replace the model adapter; keep the real verification and tool closures."""
    langchain = ModuleType('langchain')
    agent_mod = ModuleType('langchain.agents')
    tool_mod = ModuleType('langchain.tools')
    def tool(fn):
        fn.invoke = lambda data: fn(**data)
        return fn
    tool_mod.tool = tool

    def create_agent(**kwargs):
        class Fake:
            def invoke(self, messages, config):
                assert config['recursion_limit'] == 10
                execute(kwargs['tools'])
                return {'messages': []}
        return Fake()

    agent_mod.create_agent = create_agent
    monkeypatch.setitem(sys.modules, 'langchain', langchain)
    monkeypatch.setitem(sys.modules, 'langchain.agents', agent_mod)
    monkeypatch.setitem(sys.modules, 'langchain.tools', tool_mod)
    monkeypatch.setattr(agentic_supervisor, 'chat_model', lambda: 'fake')
    monkeypatch.setattr(agentic_supervisor, 'products',
                        lambda: [{'sku': 'EL-001'}, {'sku': 'EL-002'}])

    from retailiq.orchestration import agents
    class Subagent:
        def __init__(self, name): self.name = name
        def invoke(self, inputs):
            if self.name == 'sales':
                return {'result': {'records': [
                    {'sku': 'EL-001', 'name': 'AlphaBook Pro 14', 'units_sold': 10}
                ] if sales_records is None else sales_records}}
            return {'result': {'records': [
                {'sku': 'EL-001', 'on_hand': 7, 'reserved': 2, 'available': 5}
            ] if stock_records is None else stock_records}}
    monkeypatch.setattr(agents, 'build_sql_subagents',
                        lambda: (Subagent('sales'), Subagent('inventory')))
    return agentic_supervisor.agentic_replenish_review('Check top seller stock')


def test_supervisor_accepts_evidence_only_in_approved_order(monkeypatch):
    calls = []
    def execute(tools):
        calls.append(tools[0].invoke({'query':'top sellers'}))
        calls.append(tools[1].invoke({'sku':'EL-001'}))
    result = _run(monkeypatch, execute)
    assert len(calls) == 2
    assert result['subagents'] == ['sales_agent', 'inventory_agent']
    assert '5 units' in result['answer']


def test_inventory_cannot_run_before_sales(monkeypatch):
    with pytest.raises(ValueError, match='before requesting inventory'):
        _run(monkeypatch, lambda tools: tools[1].invoke({'sku':'EL-001'}))


def test_model_cannot_override_verified_top_seller_sku(monkeypatch):
    def execute(tools):
        tools[0].invoke({'query':'top sellers'})
        tools[1].invoke({'sku':'EL-002'})
    with pytest.raises(ValueError, match='top-selling SKU'):
        _run(monkeypatch, execute)


def test_supervisor_refuses_second_inventory_lookup(monkeypatch):
    def execute(tools):
        tools[0].invoke({'query':'top sellers'})
        tools[1].invoke({'sku':'EL-001'})
        tools[1].invoke({'sku':'EL-001'})
    with pytest.raises(ValueError, match='already been collected'):
        _run(monkeypatch, execute)


def test_supervisor_refuses_empty_sales_evidence(monkeypatch):
    with pytest.raises(ValueError, match='no top-seller evidence'):
        _run(monkeypatch, lambda tools: tools[0].invoke({'query':'top sellers'}),
             sales_records=[])


def test_supervisor_refuses_mismatched_inventory_evidence(monkeypatch):
    def execute(tools):
        tools[0].invoke({'query':'top sellers'})
        tools[1].invoke({'sku':'EL-001'})
    with pytest.raises(ValueError, match='mismatched SKU'):
        _run(monkeypatch, execute,
             stock_records=[{'sku': 'EL-002', 'available': 10}])


def test_supervisor_refuses_incomplete_subagent_delegation(monkeypatch):
    with pytest.raises(ValueError, match='verified sales and inventory'):
        _run(monkeypatch, lambda tools: tools[0].invoke({'query':'top sellers'}))

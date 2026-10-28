"""Run against real LangGraph if installed. No remote provider calls required.

A skipped test means LangGraph was NOT verified; CI installs the dependency.
"""
import pytest

import importlib.util
import os
if os.getenv('RETAILIQ_REQUIRE_LANGGRAPH') == 'true':
    assert importlib.util.find_spec('langgraph') is not None, 'CI must install LangGraph; missing package is a failure'
else:
    pytest.importorskip('langgraph')


def test_compiled_graph_routes_and_handoff(monkeypatch):
    from retailiq.orchestration import week1_graph as g

    class Model:
        def with_structured_output(self, schema):
            return self
        def invoke(self, messages):
            # Simulate provider-compatible structured classification.
            from types import SimpleNamespace
            q = messages[-1][1].lower()
            label = g.classify(q)
            return SimpleNamespace(intent=label)

    monkeypatch.setattr(g, 'chat_model', lambda: Model())
    graph = g.build_graph()
    sales = graph.invoke({'question': 'Which products are top sellers?'})
    assert sales['active_agent'] == 'sales_agent'
    inventory = graph.invoke({
        'question': 'How many units of the top seller are in stock?',
        'history': [{'role': 'user', 'content': 'Which products are top sellers?'}],
        'previous_agent': 'sales_agent',
    })
    assert inventory['active_agent'] == 'inventory_agent'
    assert inventory['handoff']['from'] == 'sales_agent'
    assert 'available units' in inventory['answer']


def test_compiled_supervisor_invokes_actual_subagents(monkeypatch):
    monkeypatch.setenv('RETAILIQ_SUPERVISOR_MODE', 'deterministic')
    from retailiq.orchestration import week1_graph as g
    class Model:
        def with_structured_output(self, schema):return self
        def invoke(self, messages):
            from types import SimpleNamespace
            return SimpleNamespace(intent='decision')
    monkeypatch.setattr(g, 'chat_model', lambda:Model())
    output = g.build_graph().invoke({
        'question':'Which top seller needs a replenishment review based on stock?'
    })
    assert output['active_agent'] == 'retail_supervisor'
    assert output['subagents'] == ['sales_agent','inventory_agent']
    assert output['skill'] == 'replenishment_review'
    assert 'Not a forecast' in output['answer']

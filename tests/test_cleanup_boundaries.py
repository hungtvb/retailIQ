"""Keep Week 1 public behavior while preventing the old assistant/graph coupling."""
from retailiq import assistant, queries, reply
from retailiq.orchestration import agents, week1_graph


def test_shared_query_and_reply_entrypoints():
    assert assistant.do is queries.do
    assert agents.do is queries.do
    assert week1_graph.do is queries.do
    assert week1_graph.retailiq_reply is reply.retailiq_reply

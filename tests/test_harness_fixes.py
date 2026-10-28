"""Offline verification for lesson-aligned Week 1 code hardening."""
from types import SimpleNamespace, ModuleType
import sys
import pytest
from retailiq.assistant import product_sku, do
from retailiq.orchestration.week1_graph import resolve_followup
from retailiq.orchestration.agents import review_from_evidence
from retailiq.rag import indexing


def test_sku_match_requires_explicit_unique_product():
    assert product_sku('How many AlphaBook Pro 14 units?') == 'EL-001'
    assert product_sku('How many EL-001 units?') == 'EL-001'
    assert product_sku('How many AlphaBook units?') is None
    assert product_sku('Compare EL-001 and EL-002') is None
    assert 'specify' in do('stock for AlphaBook', 'stock')['answer'].lower()


def test_context_does_not_guess_from_multi_product_answer():
    history = [{'role':'assistant',
                'content':'AlphaBook Pro 14 EL-001 and USB-C GaN Charger 65W EL-002'}]
    assert resolve_followup('What about its stock?', history) == 'What about its stock?'
    history = [{'role':'user','content':'Tell me about AlphaBook Pro 14'}]
    assert resolve_followup('What about its stock?', history).endswith('EL-001')


def test_scored_rag_filters_weak_context_and_never_syncs_on_query(monkeypatch):
    matches = [(SimpleNamespace(metadata={'source':'weak.md'}, page_content='weak'), 0.12),
               (SimpleNamespace(metadata={'source':'strong.md'}, page_content='fact'), 0.93)]
    fake = SimpleNamespace(similarity_search_with_relevance_scores=lambda q,k:matches)
    monkeypatch.setattr(indexing,'_vector_store',lambda:(fake,'unused'))
    monkeypatch.setattr(indexing,'sync_index',
                        lambda **kwargs:pytest.fail('No indexing on query path'))
    monkeypatch.setenv('RETAILIQ_RAG_MIN_RELEVANCE','0.5')
    result = indexing.vector_search('product')
    assert [r['source'] for r in result] == ['strong.md']
    monkeypatch.setenv('RETAILIQ_RAG_MIN_RELEVANCE','2')
    with pytest.raises(ValueError):indexing.vector_search('invalid')


def test_verified_replenishment_rejects_wrong_sku_and_stock_math():
    sale={'records':[{'sku':'EL-001','name':'AlphaBook Pro 14','units_sold':10}]}
    stock={'records':[{'sku':'EL-001','on_hand':7,'reserved':2,'available':5}]}
    assert '5 units' in review_from_evidence(sale,stock)['answer']
    with pytest.raises(ValueError,match='match'):
        review_from_evidence(sale,{'records':[dict(stock['records'][0],sku='EL-002')]})
    with pytest.raises(ValueError,match='Inconsistent'):
        review_from_evidence(sale,{'records':[dict(stock['records'][0],available=20)]})


def test_langsmith_metadata_and_checkpoint_thread_id_are_correlated(monkeypatch):
    from retailiq.orchestration import week1_graph as g
    from retailiq.observability import bind_context
    captured=[]
    class FakeGraph:
        def invoke(self,inp,config):
            captured.append((inp,config))
            return dict(inp,intent='stock',active_agent='inventory_agent',answer='ok')
    monkeypatch.setattr(g,'_session_graph',lambda:FakeGraph())
    with bind_context(request='req-1',session='session-1'):
        assert g.run('How much stock?')['answer']=='ok'
    state,config=captured[0]
    assert config['configurable']['thread_id']=='session-1'
    assert config['metadata']['request_id']=='req-1'
    assert state['handoff'] is None and state['subagents']==[]


def test_native_node_stream_can_forward_observed_graph_events(monkeypatch,tmp_path):
    from retailiq.orchestration import week1_graph as g
    from retailiq.observability import bind_context,bind_event_sink
    monkeypatch.setenv('RETAILIQ_NATIVE_GRAPH_EVENTS','true')
    monkeypatch.setenv('RETAILIQ_LOG_FILE',str(tmp_path/'events.jsonl'))
    class FakeGraph:
        def stream(self,inp,config,stream_mode):
            assert stream_mode=='updates'
            yield {'router':{'intent':'stock'}}
            yield {'inventory_agent':{'active_agent':'inventory_agent',
                                     'answer':'3 units','skill':'inventory_availability'}}
    monkeypatch.setattr(g,'build_graph',lambda **kw:FakeGraph())
    events=[]
    with bind_context(request='req-test'),bind_event_sink(events.append):
        assert g.run('stock')['answer']=='3 units'
    assert [e['agent'] for e in events if e['event']=='graph.node_updated']==[
        'router','inventory_agent']


def _fake_supervisor(monkeypatch, execute_tools):
    from retailiq.orchestration import agents
    from retailiq.orchestration import agentic_supervisor as a_sup
    langchain=ModuleType('langchain')
    agents_mod=ModuleType('langchain.agents')
    tools_mod=ModuleType('langchain.tools')
    def tool(fn):
        fn.invoke=lambda args:fn(**args)
        return fn
    tools_mod.tool=tool
    def create_agent(**kwargs):
        class FakeAgent:
            def invoke(self,inp,config):
                assert config['recursion_limit']==10
                execute_tools(kwargs['tools'])
                return {'messages':[{'content':'Invented number 99999'}]}
        return FakeAgent()
    agents_mod.create_agent=create_agent
    monkeypatch.setitem(sys.modules,'langchain',langchain)
    monkeypatch.setitem(sys.modules,'langchain.agents',agents_mod)
    monkeypatch.setitem(sys.modules,'langchain.tools',tools_mod)
    class FakeGraph:
        def __init__(self,domain):self.domain=domain
        def invoke(self,inp):
            if self.domain=='sales':
                return {'result':{'records':[{'sku':'EL-001','name':'AlphaBook Pro 14',
                                             'units_sold':10}]}}
            return {'result':{'records':[{'sku':'EL-001','on_hand':7,'reserved':2,
                                         'available':5}]}}
    monkeypatch.setattr(agents,'build_sql_subagents',
                        lambda:(FakeGraph('sales'),FakeGraph('inventory')))
    monkeypatch.setattr(a_sup,'chat_model',lambda:'fake-model')
    return a_sup.agentic_replenish_review


def test_supervisor_refuses_unverified_model_claim(monkeypatch):
    supervisor=_fake_supervisor(monkeypatch,lambda tools:None)
    with pytest.raises(ValueError,match='verified sales and inventory'):
        supervisor('review replenishment')


def test_supervisor_selects_scoped_subagents_and_ignores_model_numbers(monkeypatch):
    tool_outputs=[]
    def invoke_both(tools):
        tool_outputs.append(tools[0].invoke({'query':'top sellers'}))
        tool_outputs.append(tools[1].invoke({'sku':'EL-001'}))
    supervisor=_fake_supervisor(monkeypatch,invoke_both)
    result=supervisor('review replenishment')
    assert result['subagents']==['sales_agent','inventory_agent']
    assert '5 units' in result['answer'] and '99999' not in result['answer']
    assert len(tool_outputs)==2 and all('instruction' in x for x in tool_outputs)


def test_product_agent_abstains_without_source_citation(monkeypatch,tmp_path):
    from retailiq.orchestration import agents
    monkeypatch.setenv('RETAILIQ_LOG_FILE',str(tmp_path/'product.jsonl'))
    monkeypatch.setattr(agents,'do',lambda *args,**kwargs:{
        'answer':'excerpt','contexts':[{'source':'EL-001.md','text':'Document claim'}],
        'records':[]})
    class Model:
        def invoke(self,prompt):
            return SimpleNamespace(content='Unsupported model claim.',usage_metadata={})
    monkeypatch.setattr('retailiq.core.config.chat_model',lambda:Model())
    assert 'could not verify' in agents.product_analysis('tell me about product')['answer'].lower()


def test_product_agent_accepts_exact_source_cited_answer(monkeypatch,tmp_path):
    from retailiq.orchestration import agents
    monkeypatch.setenv('RETAILIQ_LOG_FILE',str(tmp_path/'cited.jsonl'))
    monkeypatch.setattr(agents,'do',lambda *args,**kwargs:{
        'answer':'excerpt','contexts':[{'source':'EL-001.md','text':'Document claim'}],
        'records':[]})
    class Model:
        def invoke(self,prompt):
            return SimpleNamespace(content='Document claim (EL-001.md).',usage_metadata={})
    monkeypatch.setattr('retailiq.core.config.chat_model',lambda:Model())
    assert agents.product_analysis('product')['answer']=='Document claim (EL-001.md).'

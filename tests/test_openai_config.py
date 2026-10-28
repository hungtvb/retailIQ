"""Provider configuration tests; fabricated keys only, zero remote requests."""
import sys
import types
import pytest
from retailiq import config


def _fake_factory(monkeypatch):
    fake=types.ModuleType('langchain_openai')
    class Fake:
        def __init__(self,**kwargs):self.kwargs=kwargs
    for name in ('ChatOpenAI','OpenAIEmbeddings'):
        setattr(fake,name,type(name,(Fake,),{}))
    monkeypatch.setitem(sys.modules,'langchain_openai',fake)


def _env(monkeypatch,url='https://demo-resource.openai.azure.com/openai/v1/',key='dummy-key'):
    monkeypatch.setenv('OPENAI_BASE_URL',url)
    monkeypatch.setenv('OPENAI_API_KEY',key)
    monkeypatch.setenv('CHAT_MODEL','demo-chat')
    monkeypatch.setenv('EMBEDDING_MODEL','demo-embed')


def test_no_creds_no_network(capsys,monkeypatch):
    monkeypatch.delenv('OPENAI_BASE_URL',raising=False)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    from scripts.check_openai import main
    monkeypatch.setattr(sys,'argv',['check_openai'])
    main()
    printed=capsys.readouterr().out
    assert 'Missing configuration' in printed
    assert 'DRY RUN' in printed


def test_same_key_url_different_models(monkeypatch):
    _fake_factory(monkeypatch);_env(monkeypatch,key='dummy-shared-key')
    chat=config.chat_model();embed=config.embeddings_model()
    assert chat.kwargs['base_url']==embed.kwargs['base_url']
    assert chat.kwargs['api_key']==embed.kwargs['api_key']=='dummy-shared-key'
    assert chat.kwargs['model']=='demo-chat'
    assert embed.kwargs['model']=='demo-embed'
    assert chat.kwargs['base_url'].endswith('/openai/v1/')
    assert 'dummy-shared-key' not in str(config.safe_status())
    assert 'demo-resource' not in str(config.safe_status())


def test_azure_root_normalized_to_v1(monkeypatch):
    _env(monkeypatch,url='https://retailiq.openai.azure.com/')
    assert config.settings().base_url=='https://retailiq.openai.azure.com/openai/v1/'


def test_custom_gateway_path_preserved(monkeypatch):
    _env(monkeypatch,url='https://gateway.example.com/tenant/abc/openai/v1')
    assert config.settings().base_url=='https://gateway.example.com/tenant/abc/openai/v1/'


def test_default_model_names(monkeypatch):
    _env(monkeypatch)
    monkeypatch.delenv('CHAT_MODEL')
    monkeypatch.delenv('EMBEDDING_MODEL')
    cfg=config.settings()
    assert cfg.chat_model==config.DEFAULT_CHAT_MODEL
    assert cfg.embedding_model==config.DEFAULT_EMBEDDING_MODEL


@pytest.mark.parametrize('url',[
    'http://not-secure.example.com/v1/',
    'https://name:secret@gateway.example.com/v1/',
    'https://gateway.example.com/v1/?api_key=secret',
    'https://gateway.example.com/v1/#token',
    'https://gateway.example.com/v1/chat/completions',
    'https://gateway.example.com/v1/embeddings',
])
def test_bad_base_urls_rejected(monkeypatch,url):
    _env(monkeypatch,url=url)
    with pytest.raises(ValueError):config.settings()


def test_langsmith_without_key_disabled(monkeypatch):
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.delenv('LANGSMITH_API_KEY',raising=False)
    assert config.configure_langsmith() is False
    assert config.os.environ['LANGSMITH_TRACING']=='false'


def test_langsmith_with_key_enabled_no_secret_echo(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.setenv('LANGSMITH_API_KEY','dummy-smith-secret')
    assert config.configure_langsmith() is True
    assert 'dummy-smith-secret' not in str(config.safe_status())


def test_graph_node_routes_with_dummy_llm(monkeypatch):
    # Offline test validates business routing and grounded generation only.
    # A real compiled LangGraph run requires the full optional dependencies.
    from retailiq.orchestration import week1_graph as graph
    from retailiq.orchestration import agents
    from retailiq import assistant
    from retailiq.core import config
    class Model:
        def invoke(self,messages):return types.SimpleNamespace(content='Grounded product description [S1]')
    monkeypatch.setattr(config,'chat_model',lambda:Model())
    monkeypatch.setattr(assistant,'retrieve',lambda q:[{'source':'EL-001','text':'EL-001 is a laptop'}])
    assert graph.classify('How many AlphaBook Pro 14 in stock?')=='stock'
    response=agents.product_analysis('Tell me about AlphaBook Pro 14')
    assert response['contexts'][0]['source']=='EL-001'
    assert 'EL-001' in response['answer']


def test_ragas_uses_one_shared_openai_client(monkeypatch):
    from pathlib import Path
    _env(monkeypatch)
    assert config.settings().chat_model != config.settings().embedding_model
    source=(Path(__file__).resolve().parents[1]/'scripts'/'eval_ragas.py').read_text()
    assert 'AsyncOpenAI(base_url=cfg.base_url,api_key=cfg.api_key)' in source
    assert 'model=cfg.embedding_model' in source

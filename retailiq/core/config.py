"""One OpenAI-compatible API endpoint/key for both chat and embeddings.

The endpoint may be OpenAI, Azure OpenAI v1 or a compatible gateway.
No credentials or full URLs are included in readiness responses or logs.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)

DEFAULT_CHAT_MODEL = 'gpt-4o-mini'
DEFAULT_EMBEDDING_MODEL = 'text-embedding-3-small'


@dataclass(frozen=True)
class OpenAISettings:
    base_url: str
    api_key: str
    chat_model: str
    embedding_model: str


def _base_url(raw: str) -> str:
    """Validate a base endpoint without mutating gateway-specific paths.

    Azure resource root URLs are normalized to /openai/v1/; other base URLs
    are passed through unchanged. Azure *classic* deployment routes need a
    version parameter and therefore are intentionally unsupported here.
    """
    url = (raw or '').strip()
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('OPENAI_BASE_URL must be a valid HTTPS endpoint')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('OPENAI_BASE_URL cannot include credentials, query or fragment')
    if parsed.path.rstrip('/').endswith(('/chat/completions','/embeddings','/responses')):
        raise ValueError('OPENAI_BASE_URL must be the API base, not a request URL')
    hostname = parsed.hostname.lower()
    if hostname.endswith(('.openai.azure.com', '.services.ai.azure.com')) and not parsed.path.strip('/'):
        url = url.rstrip('/') + '/openai/v1/'
    else:
        url = url.rstrip('/') + '/'
    return url


def settings() -> OpenAISettings:
    missing = [name for name in ('OPENAI_BASE_URL','OPENAI_API_KEY') if not os.getenv(name,'').strip()]
    if missing:
        raise ValueError('Missing configuration: ' + ', '.join(missing))
    return OpenAISettings(
        base_url=_base_url(os.environ['OPENAI_BASE_URL']),
        api_key=os.environ['OPENAI_API_KEY'].strip(),
        chat_model=os.getenv('CHAT_MODEL','').strip() or DEFAULT_CHAT_MODEL,
        embedding_model=os.getenv('EMBEDDING_MODEL','').strip() or DEFAULT_EMBEDDING_MODEL,
    )


def configure_langsmith() -> bool:
    """Remote tracing requires opt-in and its own key; never log that key."""
    enabled = os.getenv('LANGSMITH_TRACING','false').lower() in ('true','1','yes')
    if enabled and not os.getenv('LANGSMITH_API_KEY','').strip():
        os.environ['LANGSMITH_TRACING'] = 'false'
        return False
    return enabled


def _provider_timeout() -> float:
    """A per-provider-call bound, not a promise of whole-agent cancellation."""
    raw = os.getenv('RETAILIQ_PROVIDER_TIMEOUT_SECONDS', '20')
    try:
        seconds = float(raw)
    except ValueError as error:
        raise ValueError('Invalid RETAILIQ_PROVIDER_TIMEOUT_SECONDS') from error
    if not 1 <= seconds <= 120:
        raise ValueError('RETAILIQ_PROVIDER_TIMEOUT_SECONDS must be between 1 and 120')
    return seconds


def chat_model():
    from langchain_openai import ChatOpenAI
    cfg = settings()
    temperature = os.getenv('LLM_TEMPERATURE','').strip()
    extra = {'temperature':float(temperature)} if temperature else {}
    return ChatOpenAI(base_url=cfg.base_url,api_key=cfg.api_key,model=cfg.chat_model,
                      timeout=_provider_timeout(), max_retries=1, **extra)


def embeddings_model():
    from langchain_openai import OpenAIEmbeddings
    cfg = settings()
    return OpenAIEmbeddings(base_url=cfg.base_url,api_key=cfg.api_key,model=cfg.embedding_model,
                            request_timeout=_provider_timeout(), max_retries=1)


def safe_status() -> dict:
    """Exposes only readiness/selected model IDs, never URL/key/token."""
    result={'mode':os.getenv('RETAILIQ_MODE','offline'),'langsmith_enabled':configure_langsmith()}
    try:
        cfg=settings()
        result.update({'provider_ready':True,'chat_model':cfg.chat_model,'embedding_model':cfg.embedding_model})
    except ValueError as exc:
        result.update({'provider_ready':False,'error':str(exc)})
    return result

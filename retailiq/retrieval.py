"""Backwards-compatible retrieval API; implementation lives in retailiq.rag."""
import os
import re
from .rag.indexing import plan_chunks, vector_search


def lexical(question: str) -> list[dict]:
    """Offline lexical demo. This is NOT vector retrieval or LangChain RAG."""
    qwords = set(re.findall(r'[\w-]+', question.casefold())) - {'what','is','the','a','about','tell','me','of','product'}
    docs, errors = plan_chunks(strict=False)
    if errors:
        # A partial corpus may omit relevant product facts and produce
        # misleading answers. Do not silently serve incomplete evidence.
        raise ValueError('Offline knowledge ingestion is incomplete; repair unreadable documents')
    ranked = []
    for chunks in docs.values():
        for chunk in chunks:
            words = set(re.findall(r'[\w-]+', chunk['text'].casefold()))
            score = len(qwords & words)
            if score:
                ranked.append((score, chunk))
    ranked.sort(key=lambda x:(-x[0],x[1]['metadata']['source'],x[1]['id']))
    return [{'source':x['metadata']['source'], 'text':x['text'], 'metadata':x['metadata']}
            for _,x in ranked[:3]]


def retrieve(question: str) -> list[dict]:
    if os.getenv('RETAILIQ_MODE') != 'full':
        return lexical(question)
    strategy = os.getenv('RETAILIQ_RAG_RETRIEVAL', 'hybrid').strip().lower()
    if strategy == 'vector':
        return vector_search(question)
    if strategy == 'hybrid':
        from .rag.advanced_retrieval import hybrid_search
        return hybrid_search(question)
    raise ValueError('RETAILIQ_RAG_RETRIEVAL must be vector or hybrid')

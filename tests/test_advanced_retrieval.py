"""Week 2 Advanced RAG acceptance: real local corpus, fake vector transport.

Assertions cover deterministic rewriting, manifest-verified hybrid retrieval,
reranking, changed source refusal and mode selection. This does not claim
provider-backed embeddings/LLM quality or RAGAS.
"""
from __future__ import annotations

import pytest

from retailiq import retrieval
from retailiq.rag import indexing
from retailiq.rag import advanced_retrieval as advanced


class FakeStore:
    def __init__(self):
        self.documents = {}
        self.vector_override = None

    def add_documents(self, documents, ids):
        for doc, key in zip(documents, ids):
            self.documents[key] = doc

    def delete(self, ids):
        for key in ids:
            self.documents.pop(key, None)

    def similarity_search_with_relevance_scores(self, question, k):
        if self.vector_override is not None:
            if isinstance(self.vector_override, Exception):
                raise self.vector_override
            return self.vector_override[:k]
        return [(doc, 0.65) for doc in list(self.documents.values())[:k]]


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    product_docs = tmp_path / 'data' / 'product_docs'
    product_docs.mkdir(parents=True)
    (product_docs / 'EL-003.md').write_text(
        'USB-C GaN Charger 65W. Single-port output up to 65W. '
        'Supports Power Delivery 3.0. Warranty 12 months.', encoding='utf8')
    (product_docs / 'EL-001.md').write_text(
        'AlphaBook Pro 14: 14-inch display, 16GB RAM. Warranty 12 months.',
        encoding='utf8')
    (product_docs / 'EL-002.md').write_text(
        'NovaPhone X: OLED 6.2-inch screen, USB-C 25W charging.',
        encoding='utf8')
    store = FakeStore()
    manifest = tmp_path / 'index_manifest.json'
    monkeypatch.setattr(indexing, 'ROOT', tmp_path)
    monkeypatch.setattr(indexing, 'DOCS', product_docs)
    monkeypatch.setattr(indexing, 'KNOWLEDGE', tmp_path / 'data' / 'knowledge')
    monkeypatch.setattr(indexing, '_vector_store', lambda: (store, manifest))
    assert indexing.sync_index(store=store, manifest_path=manifest)['files'] == 3
    return store, manifest, product_docs


def test_deterministic_query_rewrite_retains_original_sku_and_scope():
    question = 'Thông số công suất sạc EL-003 là gì?'
    revised = advanced.rewrite_product_query(question)
    assert question in revised
    assert 'EL-003' in revised and 'power watts' in revised
    assert 'charger' in revised and 'specifications' in revised


def test_hybrid_merges_vector_and_lexical_and_prefers_matching_product(corpus):
    store, _, _ = corpus
    # Vector relevance ranks the wrong product first. Lexical match and
    # reranking must recover the named SKU's source.
    wrong = next(doc for doc in store.documents.values()
                 if doc.metadata['product_sku'] == 'EL-002')
    correct = next(doc for doc in store.documents.values()
                   if doc.metadata['product_sku'] == 'EL-003')
    store.vector_override = [(wrong, 0.91), (correct, 0.8)]
    results = advanced.hybrid_search('Thông số công suất sạc EL-003 là gì?')
    assert results and results[0]['metadata']['product_sku'] == 'EL-003'
    assert set(results[0]['retrieval_methods']) == {'vector', 'lexical'}
    assert len({r['metadata']['source_id'] for r in results}) == len(results)
    assert all(r['rewrite_strategy'] == 'deterministic_term_expansion' for r in results)


def test_lexical_supports_low_vector_similarity_without_faking_vectors(corpus):
    store, _, _ = corpus
    store.vector_override = []
    results = advanced.hybrid_search('USB-C GaN Charger 65W specifications')
    assert results and results[0]['metadata']['product_sku'] == 'EL-003'
    assert results[0]['retrieval_methods'] == ['lexical']


def test_hybrid_rejects_changed_source_before_answer(corpus):
    _, _, docs = corpus
    (docs / 'EL-003.md').write_text('Unauthorized new claim about product warranties')
    with pytest.raises(indexing.IndexNotReadyError, match='re-index'):
        advanced.hybrid_search('USB-C GaN Charger 65W warranty')


def test_hybrid_rejects_dirty_manifest_even_if_vector_returns_results(corpus):
    _, manifest, _ = corpus
    indexing._recovery_path(manifest).write_text('{"affected_ids":[]}')
    with pytest.raises(indexing.IndexNotReadyError, match='recovery'):
        advanced.hybrid_search('USB-C charger product details')


def test_hybrid_never_accepts_external_vector_document(corpus):
    store, _, _ = corpus
    from langchain_core.documents import Document
    injected = Document(page_content='Invented 1000W output',
                        metadata={'source':'evil.md','source_id':'not-indexed'})
    store.vector_override = [(injected, 1.0)]
    results = advanced.hybrid_search('Invented 1000W output')
    assert not any(r['source'] == 'evil.md' or 'Invented' in r['text'] for r in results)


def test_vector_timeout_is_not_replaced_with_unverified_lexical_answer(corpus):
    store, _, _ = corpus
    store.vector_override = TimeoutError('Provider unavailable')
    with pytest.raises(TimeoutError):
        advanced.hybrid_search('Charger specifications')


def test_retrieval_mode_dispatch(monkeypatch):
    monkeypatch.setenv('RETAILIQ_MODE', 'full')
    monkeypatch.setenv('RETAILIQ_RAG_RETRIEVAL', 'hybrid')
    monkeypatch.setattr(advanced, 'hybrid_search', lambda q: [{'source':'hybrid'}])
    assert retrieval.retrieve('product specifications') == [{'source':'hybrid'}]
    monkeypatch.setenv('RETAILIQ_RAG_RETRIEVAL', 'vector')
    monkeypatch.setattr(retrieval, 'vector_search', lambda q: [{'source':'vector'}])
    assert retrieval.retrieve('product specifications') == [{'source':'vector'}]
    monkeypatch.setenv('RETAILIQ_RAG_RETRIEVAL', 'unknown')
    with pytest.raises(ValueError, match='vector or hybrid'):
        retrieval.retrieve('product specifications')

"""Incremental Chroma sync: only changed files are re-embedded.

Manifest is local and keyed by document path/content hash. A separate Chroma
namespace is used for each embedding model/endpoint pair.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import os
import re
import zipfile
import math
import tempfile
import threading
from .loaders import SUPPORTED_FORMATS, DEFAULT_MAX_FILE_BYTES, load_file
from .chunking import split_sections

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'data' / 'product_docs'
KNOWLEDGE = ROOT / 'data' / 'knowledge'
MAX_INDEX_FILES = 1000
MAX_TOTAL_CHUNKS = 10_000


def input_paths(roots: list[Path] | None = None) -> list[Path]:
    """Only documents inside the two configured local knowledge folders."""
    roots = [DOCS, KNOWLEDGE] if roots is None else roots
    files = []
    for base in roots:
        if not base.exists():
            continue
        for item in sorted(base.rglob('*')):
            if item.is_symlink() or not item.is_file() or item.suffix.lower() not in SUPPORTED_FORMATS:
                continue
            if not item.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError('Knowledge path escapes project root')
            files.append(item)
    if len(files) > MAX_INDEX_FILES:
        raise ValueError('Knowledge corpus exceeds configured file budget')
    return files


def plan_chunks(paths: list[Path] | None = None, *, strict: bool = True) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Extract and chunk source files; no embedding/network needed."""
    documents = {}
    errors = {}
    total_chunks = 0
    for path in paths if paths is not None else input_paths():
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Knowledge document path is not permitted')
        relative = path.relative_to(ROOT).as_posix()
        try:
            sections = load_file(path)
            chunks = split_sections(sections, relative)
            if not chunks:
                raise ValueError('No readable text content')
            if len(chunks) > 1500:
                raise ValueError('Document exceeds chunk budget')
            if total_chunks + len(chunks) > MAX_TOTAL_CHUNKS:
                raise ValueError('Corpus exceeds global chunk budget')
            total_chunks += len(chunks)
            documents[relative] = chunks
        except Exception as exc:
            # Format parsers raise their own exception families (PDF, ZIP, XML).
            # Strict indexing fails; non-strict lexical mode records the failed
            # document but never silently treats it as trusted content.
            # Parser exceptions may contain source snippets; don't expose them
            # in user-facing/indexing error summaries.
            reason = type(exc).__name__
            if strict:
                raise ValueError(f'Unable to ingest {relative}: {reason}') from exc
            errors[relative] = reason
    return documents, errors


def _document_sha256(path: Path) -> str:
    """Hash files in bounded chunks; reject oversized input before reading it."""
    if path.stat().st_size > DEFAULT_MAX_FILE_BYTES:
        raise ValueError('Document exceeds configured size limit')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(64 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _vector_store():
    from langchain_chroma import Chroma
    from retailiq.core.config import settings, embeddings_model
    cfg = settings()
    namespace = hashlib.sha256(f'{cfg.base_url}|{cfg.embedding_model}'.encode()).hexdigest()[:12]
    persistence = ROOT / '.chroma' / namespace
    persistence.mkdir(parents=True, exist_ok=True)
    db = Chroma(collection_name='retailiq_products',
                embedding_function=embeddings_model(), persist_directory=str(persistence))
    return db, persistence / 'index_manifest.json'


class IndexNotReadyError(RuntimeError):
    """Index is absent, inconsistent or undergoing recovery; do not serve RAG."""


_INDEX_SYNC_LOCK = threading.Lock()


def _read_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('Manifest must be an object')
        for source, item in value.items():
            if (not isinstance(source, str) or not isinstance(item, dict)
                    or not isinstance(item.get('sha256'), str)
                    or not isinstance(item.get('ids'), list)
                    or not all(isinstance(i, str) and i for i in item['ids'])):
                raise ValueError('Invalid index manifest entry')
        return value
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise IndexNotReadyError('Product index manifest is unreadable or invalid') from exc


def _atomic_json(path: Path, data: dict) -> None:
    """Flush a complete manifest/journal before replacing the visible file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp',
                                         encoding='utf-8', delete=False) as temp:
            name = Path(temp.name)
            json.dump(data, temp, indent=2, ensure_ascii=False)
            temp.flush()
            os.fsync(temp.fileno())
        name.replace(path)
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


def _recovery_path(manifest_path: Path) -> Path:
    return manifest_path.with_name(manifest_path.name + '.dirty.json')


def sync_index(*, force: bool = False, store=None, manifest_path: Path | None = None) -> dict:
    """Synchronize with a crash-recovery journal, never trust a half-built index.

    Chroma and a JSON manifest cannot commit atomically together. A durable
    journal therefore blocks retrieval before the first vector mutation and
    records old/new chunk IDs for a deterministic cleanup on the next sync.
    Concurrency is limited to one index writer per local process.
    """
    if not _INDEX_SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError('Product index synchronization is already running')
    try:
        if store is None or manifest_path is None:
            default_store, default_manifest = _vector_store()
            store = store if store is not None else default_store
            manifest_path = manifest_path if manifest_path is not None else default_manifest
        manifest_path = Path(manifest_path)
        pending = _recovery_path(manifest_path)
        old = _read_manifest(manifest_path)
        current_paths = input_paths()
        if len(current_paths) > MAX_INDEX_FILES:
            raise ValueError('Knowledge corpus exceeds configured file budget')
        current = {p.relative_to(ROOT).as_posix(): p for p in current_paths}
        # Plan all document IDs before any vector write, so the recovery record
        # knows even chunks inserted immediately before an embedding failure.
        hashes = {name: _document_sha256(path) for name, path in current.items()}
        recovering = pending.exists()
        if recovering:
            try:
                journal = json.loads(pending.read_text(encoding='utf-8'))
                prior_ids = journal['affected_ids']
                if not isinstance(prior_ids, list) or not all(
                        isinstance(i, str) and i for i in prior_ids):
                    raise ValueError('Invalid recovery ID list')
            except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
                raise IndexNotReadyError('Product index recovery journal is invalid') from exc
        else:
            prior_ids = []
        changed = {name for name in current if force or recovering or
                   name not in old or old[name]['sha256'] != hashes[name]}
        removed = sorted(set(old) - set(current))
        if not changed and not removed and not recovering:
            if not manifest_path.exists():
                _atomic_json(manifest_path, {})
            return {'updated': [], 'unchanged': sorted(current),
                    'removed': [], 'files': len(old),
                    'chunks': sum(len(x['ids']) for x in old.values())}

        planned: dict[str, list[dict]] = {}
        for name in sorted(current if recovering else changed):
            docs, _errors = plan_chunks([current[name]])
            planned[name] = docs[name]
        total_committed = sum(
            len(item['ids']) for name, item in old.items()
            if name in current and name not in planned)
        if total_committed + sum(len(entries) for entries in planned.values()) > MAX_TOTAL_CHUNKS:
            raise ValueError('Corpus exceeds global chunk budget')
        changed_ids = [chunk['id'] for entries in planned.values() for chunk in entries]
        affected = sorted(set(prior_ids)
                          | {id_ for name in (old if recovering else changed | set(removed))
                             for id_ in old.get(name, {}).get('ids', [])}
                          | set(changed_ids))
        # Make all partial vector mutations invisible to query readers before
        # Chroma is touched. Preserve journal if upsert/delete/embedding fails.
        _atomic_json(pending, {'affected_ids': affected})
        from langchain_core.documents import Document
        try:
            if recovering:
                if affected:
                    store.delete(ids=affected)
            for name in sorted(planned):
                entries = planned[name]
                docs = [Document(page_content=e['text'], metadata=e['metadata']) for e in entries]
                ids = [e['id'] for e in entries]
                store.add_documents(docs, ids=ids)
                if not recovering:
                    obsolete = sorted(set(old.get(name, {}).get('ids', [])) - set(ids))
                    if obsolete:
                        store.delete(ids=obsolete)
            if not recovering:
                for name in removed:
                    ids = old[name].get('ids', [])
                    if ids:
                        store.delete(ids=ids)
            next_manifest = dict(old)
            for name, entries in planned.items():
                next_manifest[name] = {'sha256': hashes[name],
                                       'ids': [e['id'] for e in entries]}
            for name in removed:
                next_manifest.pop(name, None)
            _atomic_json(manifest_path, next_manifest)
        except Exception:
            # The journal survives; next sync reconciles known IDs.
            raise
        pending.unlink()
        return {'updated': sorted(planned),
                'unchanged': sorted(set(current) - set(planned)),
                'removed': removed, 'files': len(next_manifest),
                'chunks': sum(len(v['ids']) for v in next_manifest.values())}
    finally:
        _INDEX_SYNC_LOCK.release()


def vector_search(question: str, k: int = 3) -> list[dict]:
    """Return verified, source-addressable document chunks or abstain.

    A matching filename is not sufficient: the source and chunk ID must be in
    the last committed manifest. A dirty, missing or malformed index cannot
    be queried; rerun scripts/index_products.py to reconcile it.
    """
    if not _INDEX_SYNC_LOCK.acquire(blocking=False):
        raise IndexNotReadyError('Product index is being updated')
    try:
        if not isinstance(question, str) or not 3 <= len(question.strip()) <= 500:
            raise ValueError('RAG question must be 3–500 characters')
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 10:
            raise ValueError('RAG k must be between 1 and 10')
        raw = os.getenv('RETAILIQ_RAG_MIN_RELEVANCE', '0.45')
        try:
            threshold = float(raw)
        except ValueError as exc:
            raise ValueError('Invalid RETAILIQ_RAG_MIN_RELEVANCE') from exc
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError('RETAILIQ_RAG_MIN_RELEVANCE must be finite and between 0 and 1')
        db, manifest_path = _vector_store()
        if _recovery_path(manifest_path).exists():
            raise IndexNotReadyError('Product index recovery is required before querying')
        if not manifest_path.is_file():
            raise IndexNotReadyError('Product index missing; run scripts/index_products.py')
        manifest = _read_manifest(manifest_path)
        if not manifest:
            return []  # Successfully indexed empty corpus is not a provider failure.
        matches = db.similarity_search_with_relevance_scores(question.strip(), k=k)
        contexts = []
        seen = set()
        for doc, value in matches:
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(score) or not threshold <= score <= 1:
                continue
            metadata = getattr(doc, 'metadata', None)
            if not isinstance(metadata, dict):
                continue
            source, chunk_id = metadata.get('source'), metadata.get('source_id')
            if (not isinstance(source, str) or not isinstance(chunk_id, str)
                    or source not in manifest or chunk_id not in manifest[source]['ids']
                    or chunk_id in seen):
                continue
            content = getattr(doc, 'page_content', None)
            if not isinstance(content, str) or not content.strip():
                continue
            seen.add(chunk_id)
            contexts.append({'source': source, 'text': content[:2400],
                             'metadata': metadata, 'relevance_score': round(score, 4)})
            if len(contexts) >= k:
                break
        return contexts
    finally:
        _INDEX_SYNC_LOCK.release()

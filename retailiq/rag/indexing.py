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


def input_paths(roots: list[Path] | None = None) -> list[Path]:
    """Only documents inside the two configured local knowledge folders."""
    roots = roots or [DOCS, KNOWLEDGE]
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
    return files


def plan_chunks(paths: list[Path] | None = None, *, strict: bool = True) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Extract and chunk source files; no embedding/network needed."""
    documents = {}
    errors = {}
    for path in paths if paths is not None else input_paths():
        relative = path.relative_to(ROOT).as_posix()
        try:
            sections = load_file(path)
            chunks = split_sections(sections, relative)
            if not chunks:
                raise ValueError('No readable text content')
            documents[relative] = chunks
        except (OSError, UnicodeError, ValueError, ImportError, KeyError, IndexError, RuntimeError, zipfile.BadZipFile) as exc:
            if strict:
                raise ValueError(f'Unable to ingest {relative}: {type(exc).__name__}: {exc}') from exc
            errors[relative] = f'{type(exc).__name__}: {exc}'
    return documents, errors


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
        current = {p.relative_to(ROOT).as_posix(): p for p in current_paths}
        # Plan all document IDs before any vector write, so the recovery record
        # knows even chunks inserted immediately before an embedding failure.
        hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for name, path in current.items()}
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
            return {'updated': [], 'unchanged': sorted(current),
                    'removed': [], 'files': len(old),
                    'chunks': sum(len(x['ids']) for x in old.values())}

        planned: dict[str, list[dict]] = {}
        for name in sorted(current if recovering else changed):
            docs, _errors = plan_chunks([current[name]])
            planned[name] = docs[name]
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
    """Reject weak document matches and abstain when evidence is insufficient.

    Relevance threshold is an uncalibrated starting point; adjust via evaluation.
    Product index is built separately with scripts/index_products.py.
    """
    db, _manifest = _vector_store()
    threshold = float(os.getenv('RETAILIQ_RAG_MIN_RELEVANCE', '0.45'))
    if not (0 <= threshold <= 1):
        raise ValueError('RETAILIQ_RAG_MIN_RELEVANCE must be between 0 and 1')
    matches = db.similarity_search_with_relevance_scores(question, k=k)
    return [{'source': d.metadata.get('source', 'unknown'), 'text': d.page_content,
             'metadata': d.metadata, 'relevance_score': round(float(score), 4)}
            for d, score in matches if score >= threshold and d.page_content.strip()]

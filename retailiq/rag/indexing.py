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


def sync_index(*, force: bool = False, store=None, manifest_path: Path | None = None) -> dict:
    """Incremental local indexing. `store`/`manifest_path` enable network-free tests."""
    if store is None or manifest_path is None:
        default_store, default_manifest = _vector_store()
        store = store or default_store
        manifest_path = manifest_path or default_manifest
    old = {}
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding='utf-8'))
    current_paths = input_paths()
    current = {p.relative_to(ROOT).as_posix(): p for p in current_paths}
    next_manifest = dict(old)
    updated = []
    skipped = []
    removed = []
    for relative, path in current.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not force and relative in old and old[relative].get('sha256') == digest:
            skipped.append(relative)
            continue
        chunks, _ = plan_chunks([path])
        entries = chunks[relative]
        from langchain_core.documents import Document
        docs = [Document(page_content=e['text'], metadata=e['metadata']) for e in entries]
        ids = [e['id'] for e in entries]
        # New/changed document is embedded before stale chunks are removed.
        store.add_documents(docs, ids=ids)
        previous = set(old.get(relative, {}).get('ids', []))
        obsolete = sorted(previous - set(ids))
        if obsolete:
            store.delete(ids=obsolete)
        next_manifest[relative] = {'sha256': digest, 'ids': ids}
        updated.append(relative)
    for relative in set(old) - set(current):
        ids = old[relative].get('ids', [])
        if ids:
            store.delete(ids=ids)
        next_manifest.pop(relative, None)
        removed.append(relative)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp = manifest_path.with_suffix('.tmp')
    temp.write_text(json.dumps(next_manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(manifest_path)
    return {'updated': updated, 'unchanged': skipped, 'removed': sorted(removed),
            'files': len(next_manifest), 'chunks': sum(len(v['ids']) for v in next_manifest.values())}


def vector_search(question: str, k: int = 3) -> list[dict]:
    db, manifest = _vector_store()
    sync_index(store=db, manifest_path=manifest)
    matches = db.similarity_search(question, k=k)
    return [{'source': d.metadata.get('source', 'unknown'), 'text': d.page_content,
             'metadata': d.metadata} for d in matches]

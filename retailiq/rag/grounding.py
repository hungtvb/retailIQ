"""Small, testable product-answer evidence contract.

LLM-visible document content is UNTRUSTED. A citation marker is evidence of a
referenced chunk, not a proof that every generated claim is entailed by it.
"""
from __future__ import annotations

import json
import re

MAX_CONTEXTS = 3
MAX_CONTEXT_CHARS = 2400
MAX_ANSWER_CHARS = 5000
CITATION = re.compile(r'\[S([1-9][0-9]*)\]')


def build_evidence(contexts: list[dict]) -> tuple[str, dict[str, str]]:
    """Return bounded, safely serialized untrusted documents and their labels."""
    if not isinstance(contexts, list):
        raise ValueError('Retrieved contexts must be a list')
    packets = []
    labels = {}
    for context in contexts[:MAX_CONTEXTS]:
        if not isinstance(context, dict):
            continue
        source, text = context.get('source'), context.get('text')
        if not isinstance(source, str) or not source.strip():
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        ref = f'S{len(packets)+1}'
        labels[ref] = source
        packets.append({'citation': '[' + ref + ']', 'source': source,
                        'untrusted_text': text[:MAX_CONTEXT_CHARS]})
    return json.dumps(packets, ensure_ascii=False), labels


def validate_answer(candidate: object, labels: dict[str, str]) -> tuple[bool, list[str]]:
    """Require exact citations for known retrieved chunks and reject stray refs."""
    if not isinstance(candidate, str) or not candidate.strip() or len(candidate) > MAX_ANSWER_CHARS:
        return False, []
    refs = ['S' + value for value in CITATION.findall(candidate)]
    if not refs or not all(ref in labels for ref in refs):
        return False, []
    # A citation check alone is NOT a semantic faithfulness evaluation.
    return True, list(dict.fromkeys(refs))


def attach_sources(answer: str, referenced: list[str], labels: dict[str, str]) -> str:
    """Append stable source provenance outside the model-controlled answer."""
    sources = '\n'.join(f'[{ref}]: {labels[ref]}' for ref in referenced)
    return answer.rstrip() + '\n\nSources:\n' + sources

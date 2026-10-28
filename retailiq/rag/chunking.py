"""Small chunks with stable, source-addressable metadata."""
from __future__ import annotations
from pathlib import Path
import hashlib
import re
from .loaders import TextSection


def split_sections(sections: list[TextSection], relative_path: str, *, chunk_size: int = 700,
                   overlap: int = 90) -> list[dict]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError('chunk_size must be greater than overlap >= 0')
    result = []
    filename = Path(relative_path).stem
    sku_match = re.search(r'EL-\d{3}', relative_path.upper())
    for section_number, section in enumerate(sections, 1):
        text = section.text.strip()
        start = 0
        part = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                boundary = max(text.rfind('\n', start + chunk_size // 2, end),
                               text.rfind(' ', start + chunk_size // 2, end))
                if boundary > start:
                    end = boundary
            if end <= start:
                end = min(start + chunk_size, len(text))
            part += 1
            chunk = text[start:end].strip()
            if chunk:
                digest = hashlib.sha256(f'{relative_path}:{section_number}:{part}:{chunk}'.encode()).hexdigest()[:24]
                metadata = {'source': relative_path, 'document_type': Path(relative_path).suffix.lower().lstrip('.'),
                            'section': section_number, 'chunk': part, 'source_id': digest,
                            **section.metadata}
                if sku_match:
                    metadata['product_sku'] = sku_match.group(0)
                if len(result) >= 1500:
                    raise ValueError('Document exceeds chunk budget')
                result.append({'id': digest, 'text': chunk, 'metadata': metadata})
            if end == len(text):
                break
            start = max(start+1, end - overlap)
    return result

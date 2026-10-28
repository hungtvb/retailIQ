"""Validate local multi-format document loading; no network or embedding model."""
import pytest
from pathlib import Path
from retailiq.rag.loaders import SUPPORTED_FORMATS, load_file
from retailiq.rag.indexing import plan_chunks, ROOT

FILES={
    ".md":"data/product_docs/EL-001.md",
    ".txt":"data/knowledge/shipping_policy.txt",
    ".pdf":"data/knowledge/charger_manual.pdf",
    ".docx":"data/knowledge/alphabook_guide.docx",
    ".csv":"data/knowledge/accessory_specs.csv",
    ".xlsx":"data/knowledge/compatibility_matrix.xlsx",
    ".json":"data/knowledge/help_articles.json",
    ".html":"data/knowledge/warranty_faq.html",
}

@pytest.mark.parametrize('ext,path',FILES.items())
def test_supported_loader_has_source_text(ext,path):
    assert ext in SUPPORTED_FORMATS
    sections=load_file(ROOT/path)
    assert len(sections)>=1
    assert all(s.text.strip() for s in sections)

def test_all_product_knowledge_files_can_chunk():
    docs,errors=plan_chunks(strict=False)
    assert not errors, errors
    assert len(docs)>=len(FILES)
    assert all(all('source' in chunk['metadata'] for chunk in entries) for entries in docs.values())

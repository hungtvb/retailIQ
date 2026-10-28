"""The quality gate must not overwrite the developer's local retail fixture."""

from datetime import date
import sqlite3

from retailiq.infrastructure import sqlite as adapter
from scripts.seed import ROOT, seed


def test_temporary_seed_is_read_by_adapter_without_touching_project_data(monkeypatch, tmp_path):
    project_db = ROOT / "data" / "retailiq.sqlite3"
    product_doc = ROOT / "data" / "product_docs" / "EL-003.md"
    original_db = project_db.read_bytes() if project_db.exists() else None
    original_doc = product_doc.read_bytes()

    fixture = tmp_path / "retailiq.sqlite3"
    seed(fixture, write_support_files=False, reference_date=date(2026, 10, 28))
    monkeypatch.setenv("RETAILIQ_DATA_DB", str(fixture))

    assert adapter.query("SELECT COUNT(*) AS total FROM products") == [{"total": 10}]
    with sqlite3.connect(fixture) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 120
    assert (project_db.read_bytes() if project_db.exists() else None) == original_db
    assert product_doc.read_bytes() == original_doc

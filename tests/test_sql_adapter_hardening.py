"""SQL adapter invariants: read-only, bounded, correctly closed and predictable failure."""
import sqlite3

import pytest

from retailiq.infrastructure import sqlite as adapter


@pytest.fixture
def populated_db(tmp_path, monkeypatch):
    path = tmp_path / 'retail.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE things (id INTEGER PRIMARY KEY, name TEXT)')
        connection.executemany('INSERT INTO things (name) VALUES (?)', [
            ('Product-' + str(i),) for i in range(250)
        ])
    monkeypatch.setattr(adapter, 'DB', path)
    return path


def test_parameterized_read_and_stable_shape(populated_db):
    rows = adapter.query(' SELECT id, name FROM things WHERE name=?', ('Product-14',))
    assert rows == [{'id': 15, 'name': 'Product-14'}]
    assert adapter.query('SELECT id FROM things WHERE name=?', ("' OR 1=1 --",)) == []


@pytest.mark.parametrize('sql', [
    'DROP TABLE things', 'DELETE FROM things', 'UPDATE things SET name="x"',
    'PRAGMA writable_schema=ON', 'SELECTED * FROM things', '',
])
def test_reject_non_select_sql(populated_db, sql):
    with pytest.raises(ValueError, match='reviewed SELECT'):
        adapter.query(sql)


def test_reject_non_sequence_parameters(populated_db):
    with pytest.raises(TypeError, match='sequence'):
        adapter.query('SELECT id FROM things WHERE name=?', {'name': 'x'})


def test_failure_and_success_both_close_sqlite_handle(populated_db, monkeypatch):
    base_connect = sqlite3.connect
    closed = []

    class TrackingConnection(sqlite3.Connection):
        def close(self):
            closed.append(True)
            return super().close()

    def connect(*args, **kwargs):
        return base_connect(*args, factory=TrackingConnection, **kwargs)

    monkeypatch.setattr(adapter.sqlite3, 'connect', connect)
    assert adapter.query('SELECT COUNT(*) AS n FROM things')[0]['n'] == 250
    with pytest.raises(sqlite3.OperationalError, match='no such table'):
        adapter.query('SELECT * FROM missing')
    assert closed == [True, True]


def test_overlarge_result_fails_before_materializing_all_rows(populated_db, monkeypatch):
    monkeypatch.setattr(adapter, 'MAX_QUERY_ROWS', 100)
    with pytest.raises(ValueError, match='row limit'):
        adapter.query('SELECT * FROM things')
    assert len(adapter.query('SELECT * FROM things LIMIT 50')) == 50


def test_long_running_sql_is_interrupted(populated_db, monkeypatch):
    monkeypatch.setattr(adapter, 'SQLITE_QUERY_SECONDS', -1.0)
    with pytest.raises(sqlite3.OperationalError, match='interrupted'):
        adapter.query('SELECT a.id, b.id FROM things a CROSS JOIN things b')


def test_missing_database_is_a_controlled_sqlite_error(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, 'DB', tmp_path / 'missing.sqlite3')
    with pytest.raises(sqlite3.OperationalError):
        adapter.query('SELECT 1 AS value')

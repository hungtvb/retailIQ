"""Business golden scenarios for UC-01: evidence-backed inventory/sales review.

Each test uses an isolated, synthetic SQLite fixture, never the seed demo DB.
No LLM or model-generated answers are needed to verify business arithmetic.
"""
from contextlib import closing
from hashlib import sha256
import sqlite3

import pytest
from fastapi.testclient import TestClient

from retailiq.api import app
from retailiq import assistant
from retailiq.domain import analytics
from retailiq.infrastructure import sqlite as adapter


QUESTION = "Which top seller needs a replenishment review based on stock?"


@pytest.fixture
def golden_db(tmp_path, monkeypatch):
    """Deliberately small, human-checkable sales/inventory truth table.

    Current month October 2026:
      SKU-A: 20 completed units, 5 available, 1,980,000 VND online
      SKU-B:  8 completed units, 12 available, 390,000 VND store
      SKU-C:  4 completed units, no inventory, 120,000 VND online

    Cancelled and outside-period orders contain 999 units each to catch
    accidental status/period inclusion. Prices and discounts are per line.
    """
    path = tmp_path / "golden-retailer.sqlite3"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript("""
            CREATE TABLE products(sku TEXT PRIMARY KEY, name TEXT, category TEXT);
            CREATE TABLE locations(id TEXT PRIMARY KEY, name TEXT, channel TEXT);
            CREATE TABLE inventory(sku TEXT, location_id TEXT, on_hand INTEGER,
                                   reserved INTEGER, updated_at TEXT);
            CREATE TABLE orders(id TEXT PRIMARY KEY, ordered_at TEXT,
                                channel TEXT, status TEXT);
            CREATE TABLE order_lines(id INTEGER PRIMARY KEY, order_id TEXT,
                                    sku TEXT, quantity INTEGER, unit_price_vnd INTEGER,
                                    discount_vnd INTEGER);
        """)
        conn.executemany("INSERT INTO products VALUES (?,?,?)", [
            ("SKU-A", "Alpha Laptop", "Laptop"),
            ("SKU-B", "Beta Charger", "Accessory"),
            ("SKU-C", "Gamma Keyboard", "Peripheral"),
        ])
        conn.executemany("INSERT INTO locations VALUES (?,?,?)", [
            ("WH", "Warehouse", "warehouse"), ("ST", "Store", "store"),
        ])
        conn.executemany("INSERT INTO inventory VALUES (?,?,?,?,?)", [
            ("SKU-A", "WH", 4, 2, "2026-10-28T09:00:00+07:00"),
            ("SKU-A", "ST", 5, 2, "2026-10-28T09:00:00+07:00"),
            ("SKU-B", "WH", 9, 2, "2026-10-28T09:00:00+07:00"),
            ("SKU-B", "ST", 6, 1, "2026-10-28T09:00:00+07:00"),
        ])
        conn.executemany("INSERT INTO orders VALUES (?,?,?,?)", [
            ("O-A", "2026-10-01", "online", "completed"),
            ("O-B", "2026-10-31", "store", "completed"),
            ("O-C", "2026-10-18", "online", "completed"),
            ("O-CANCEL", "2026-10-15", "online", "cancelled"),
            ("O-PREV", "2026-09-30", "store", "completed"),
            ("O-NEXT", "2026-11-01", "store", "completed"),
        ])
        conn.executemany("INSERT INTO order_lines VALUES (?,?,?,?,?,?)", [
            (1, "O-A", "SKU-A", 20, 100_000, 20_000),
            (2, "O-B", "SKU-B", 8, 50_000, 10_000),
            (3, "O-C", "SKU-C", 4, 30_000, 0),
            (4, "O-CANCEL", "SKU-A", 999, 100_000, 0),
            (5, "O-PREV", "SKU-A", 999, 100_000, 0),
            (6, "O-NEXT", "SKU-A", 999, 100_000, 0),
        ])
    monkeypatch.setattr(adapter, "DB", path)
    monkeypatch.setenv("RETAILIQ_MODE", "offline")
    monkeypatch.setenv("RETAILIQ_AS_OF", "2026-10-28")
    monkeypatch.setenv("RETAILIQ_LOG_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "sessions.sqlite3"))
    return path


def change(db, sql, parameters=()):
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(sql, parameters)


def decision(client):
    response = client.post("/ask", json={"question": QUESTION})
    assert response.status_code == 200, response.text[:300]
    payload = response.json()
    assert payload["mode"].startswith("OFFLINE")
    assert payload["intent"] == "decision"
    assert payload["active_agent"] == "retail_supervisor"
    return payload


def test_g01_low_available_requires_human_review(golden_db):
    value = decision(TestClient(app))
    assert value["subagents"] == ["sales_agent", "inventory_agent"]
    assert value["records"][0]["sku"] == "SKU-A"
    assert value["records"][0]["units_sold"] == 20
    inventory_rows = value["records"][1:]
    assert {row["location_id"]: row["available"] for row in inventory_rows} == {
        "ST": 3, "WH": 2
    }
    assert sum(row["available"] for row in inventory_rows) == 5
    assert "REVIEW replenishment priority" in value["answer"]
    assert "20 units" in value["answer"] and "5 available" in value["answer"]
    assert "Not a forecast or purchase order" in value["answer"]


@pytest.mark.parametrize("availability, review_required", [
    (19, True), (20, False), (21, False)
])
def test_g02_g03_threshold_is_strictly_below_monthly_sales(
    golden_db, availability, review_required
):
    # Replace stock of the winner only; ensure boundary 20 is NOT flagged.
    change(golden_db, "UPDATE inventory SET on_hand=0,reserved=0 WHERE sku='SKU-A'")
    change(golden_db, """
        UPDATE inventory SET on_hand=? WHERE sku='SKU-A' AND location_id='WH'
    """, (availability,))
    answer = decision(TestClient(app))["answer"]
    assert ("REVIEW replenishment priority" in answer) is review_required
    assert f"{availability} available" in answer


def test_g04_missing_inventory_abstains_instead_of_inventing_zero(golden_db):
    change(golden_db, "DELETE FROM inventory WHERE sku='SKU-A'")
    result = decision(TestClient(app))
    assert len(result["records"]) == 1
    assert result["records"][0]["sku"] == "SKU-A"
    assert "inventory evidence is missing" in result["answer"]
    assert "No purchasing recommendation" in result["answer"]
    assert "REVIEW replenishment priority" not in result["answer"]


def test_g05_corrupt_inventory_yields_failure_not_a_confident_decision(golden_db):
    change(golden_db, """
        UPDATE inventory SET reserved=200 WHERE sku='SKU-A' AND location_id='WH'
    """)
    response = TestClient(app).post("/ask", json={"question": QUESTION})
    assert response.status_code == 503
    assert "REVIEW replenishment priority" not in response.text
    assert "reserved=200" not in response.text


def test_g06_zero_completed_sales_does_not_invent_a_top_seller(golden_db):
    change(golden_db, "UPDATE orders SET status='cancelled'")
    result = decision(TestClient(app))
    assert result["records"] == []
    assert "No completed-order data" in result["answer"]
    assert "REVIEW replenishment priority" not in result["answer"]


def test_g07_cancelled_other_months_discounts_and_channels_are_excluded(golden_db):
    assert analytics.revenue() == [
        {"channel": "online", "orders": 2, "net_revenue_vnd": 2_100_000},
        {"channel": "store", "orders": 1, "net_revenue_vnd": 390_000},
    ]
    assert [(row["sku"], row["units_sold"]) for row in analytics.top()] == [
        ("SKU-A", 20), ("SKU-B", 8), ("SKU-C", 4)
    ]
    data = TestClient(app).post("/ask", json={
        "question": "What is revenue this month?"
    }).json()
    assert data["intent"] == "revenue"
    assert data["as_of"] == "2026-10"
    assert sum(row["net_revenue_vnd"] for row in data["records"]) == 2_490_000
    assert "after line discounts" in data["answer"]


def test_g08_equal_units_top_seller_resolves_deterministically_by_sku(golden_db):
    change(golden_db, "UPDATE order_lines SET quantity=20 WHERE id=2")
    leaders = analytics.top()
    assert [(row["sku"], row["units_sold"]) for row in leaders[:2]] == [
        ("SKU-A", 20), ("SKU-B", 20)
    ]
    assert decision(TestClient(app))["records"][0]["sku"] == "SKU-A"


def test_g09_unknown_or_ambiguous_product_requires_clarification(golden_db):
    client = TestClient(app)
    for question in (
        "How many units of SKU-UNKNOWN are in stock?",
        "How many units of Alpha Laptop and Beta Charger are in stock?",
    ):
        payload = client.post("/ask", json={"question": question}).json()
        assert payload["intent"] == "stock"
        assert payload["records"] == []
        assert "specify a known product name or SKU" in payload["answer"]


def test_g10_same_sku_availability_has_independent_location_evidence(golden_db):
    payload = TestClient(app).post("/ask", json={
        "question": "How many units of SKU-A are in stock?"
    }).json()
    assert payload["intent"] == "stock"
    assert [row["location_id"] for row in payload["records"]] == ["ST", "WH"]
    assert sum(row["available"] for row in payload["records"]) == 5
    assert all(
        row["available"] == row["on_hand"] - row["reserved"]
        for row in payload["records"]
    )
    assert "5 available units" in payload["answer"]


def test_g11_missing_period_and_december_rollover_do_not_reuse_october_sales(
    golden_db, monkeypatch
):
    monkeypatch.setenv("RETAILIQ_AS_OF", "2026-12-28")
    assert analytics._month_bounds() == ("2026-12-01", "2027-01-01")
    assert analytics.top() == []
    assert analytics.revenue() == []
    result = decision(TestClient(app))
    assert result["as_of"] == "2026-12"
    assert result["records"] == []
    assert "REVIEW replenishment priority" not in result["answer"]


def test_g12_orphan_sku_in_completed_sales_is_rejected(golden_db):
    change(golden_db, "UPDATE order_lines SET sku='MISSING' WHERE id=1")
    response = TestClient(app).post("/ask", json={"question": QUESTION})
    assert response.status_code == 503
    assert "REVIEW replenishment priority" not in response.text


def test_g13_demo_retail_data_remains_read_only_across_requests(golden_db):
    before = sha256(golden_db.read_bytes()).hexdigest()
    client = TestClient(app)
    for question in (
        QUESTION,
        "Which products are top sellers?",
        "What is revenue this month?",
        "How many units of SKU-A are in stock?",
    ):
        assert client.post("/ask", json={"question": question}).status_code == 200
    assert sha256(golden_db.read_bytes()).hexdigest() == before


def test_g14_old_timestamp_is_not_a_freshness_sla(golden_db):
    """Known Week 2 gap: validation currently checks timezone, not maximum age."""
    change(golden_db, """
        UPDATE inventory SET updated_at='2025-01-01T09:00:00+07:00'
        WHERE sku='SKU-A'
    """)
    rows = analytics.inventory("SKU-A")
    assert rows and all(row["updated_at"].startswith("2025-01-01") for row in rows)
    # Existing Week 1 code still applies the illustrative heuristic. DO NOT
    # mistake this for freshness-aware safe replenishment advice.
    assert "REVIEW replenishment priority" in decision(TestClient(app))["answer"]

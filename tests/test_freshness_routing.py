"""W2-01 source selection and freshness evidence: deterministic integration tests.

No production SLA, live order feed or real-time source is claimed.
"""
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

from retailiq.domain.freshness_routing import route_freshness
from retailiq.domain.semantic import contracts
from retailiq.api import app
from scripts.seed import seed

NOW = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)


def locations(*ages):
    return [
        {"location_id": f"ST-{i}", "updated_at": (NOW-timedelta(seconds=age)).isoformat()}
        for i, age in enumerate(ages)
    ]


@pytest.mark.parametrize("metric,source,tier,tool", [
    ("available_stock", "inventory", "15_min", "inventory"),
    ("net_revenue", "completed_orders", "hourly", "revenue"),
    ("top_sellers", "completed_orders", "daily", "top"),
    ("product_knowledge", "product_documents", "daily", "vector_search"),
    ("order_state", "orders_mcp", "live", "order_lookup"),
])
def test_routes_all_required_source_tiers_without_invented_freshness(metric, source, tier, tool):
    result = route_freshness(metric, now=NOW)
    assert (result["source"], result["baseline_tier"],
            result["selected_tool"]) == (source, tier, tool)
    assert result["status"] == "UNVERIFIED"
    assert result["tool_execution"] == "not_executed_by_router"
    assert result["guaranteed"] is False


def test_aggregate_inventory_uses_oldest_location():
    fresh = route_freshness("available_stock", inventory_rows=locations(60, 899, 10), now=NOW)
    stale = route_freshness("available_stock", inventory_rows=locations(60, 901, 10), now=NOW)
    edge = route_freshness("available_stock", inventory_rows=locations(0, 900, 100), now=NOW)
    assert fresh["status"] == "PASS" and fresh["checked_records"] == 3
    assert stale["status"] == "STALE" and stale["age_seconds"] == 901
    assert edge["status"] == "PASS"
    assert fresh["observed_at"] == (NOW-timedelta(seconds=899)).isoformat()


def test_live_request_never_treats_sql_snapshot_as_real_time():
    result = route_freshness("available_stock", requested_tier="live",
                             inventory_rows=locations(0), now=NOW)
    assert result["applied_tier"] == "live"
    assert result["status"] == "UNVERIFIED"
    assert not result["meets_target"]
    assert "snapshot" in result["reason"].lower()


def test_caller_cannot_relax_inventory_target_to_daily():
    result = route_freshness("available_stock", requested_tier="daily",
                             inventory_rows=locations(1200), now=NOW)
    assert result["requested_tier"] == "daily"
    assert result["applied_tier"] == "15_min"
    assert result["status"] == "STALE"


@pytest.mark.parametrize("bad", [
    [], [{"location_id": "A", "updated_at": "bad"}],
    [{"location_id": "A", "updated_at": "2026-10-30T08:00:00"}],
    [{"location_id": "A", "updated_at": None}],
])
def test_absent_or_bad_inventory_timestamps_never_pass(bad):
    if not bad:
        assert route_freshness("available_stock", inventory_rows=bad, now=NOW)["status"] == "UNVERIFIED"
    else:
        with pytest.raises(ValueError, match="timestamp"):
            route_freshness("available_stock", inventory_rows=bad, now=NOW)


def test_duplicate_location_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        route_freshness("available_stock", inventory_rows=[
            {"location_id": "A", "updated_at": NOW.isoformat()},
            {"location_id": "A", "updated_at": NOW.isoformat()},
        ], now=NOW)


def test_any_future_update_fails_even_when_oldest_is_valid():
    result = route_freshness("available_stock",
                             inventory_rows=locations(-10, 100), now=NOW)
    assert result["status"] == "STALE"
    assert "future" in result["reason"].lower()


def test_no_freshness_claim_from_order_creation_timestamp():
    result = route_freshness("order_state", requested_tier="live",
                             now=NOW)
    assert result["source"] == "orders_mcp"
    assert result["selected_transport"] == "mcp_stdio"
    assert result["status"] == "UNVERIFIED"


def test_semantic_contracts_include_all_five_metrics_and_tiers():
    c = contracts()
    for metric in ("available_stock", "net_revenue", "top_sellers",
                   "order_state", "product_knowledge"):
        assert metric in c["metrics"]
    assert set(c["freshness_tiers"]) == {"live", "15_min", "hourly", "daily"}
    assert all(not tier["guaranteed"] for tier in c["freshness_tiers"].values())


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / 'business.sqlite3'
    seed(path, write_support_files=False)
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    monkeypatch.setenv('RETAILIQ_DATA_DB', str(path))
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'chat.sqlite3'))
    monkeypatch.setenv('RETAILIQ_WORKFLOW_DB', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RETAILIQ_WORKFLOW_USE_MCP', '0')
    with TestClient(app) as c:
        yield c, path


def test_freshness_route_api_reads_actual_sql_timestamps(client):
    c, db = client
    with sqlite3.connect(db) as con:
        stamp = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        con.execute("UPDATE inventory SET updated_at=? WHERE sku='EL-003'", (stamp,))
    response = c.post('/api/workflows/freshness/route', json={
        'metric': 'available_stock', 'sku': 'EL-003',
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'PASS'
    assert result['checked_records'] == 3
    assert result['tool_execution'] == 'executed_readonly'
    assert result['execution_mode'] == 'local_sqlite'
    assert result['source'] == 'inventory'
    assert result['guaranteed'] is False
    assert result['age_seconds'] >= 0


def test_freshness_route_api_detects_single_stale_location(client):
    c, db = client
    with sqlite3.connect(db) as con:
        stamp = datetime.now(timezone.utc).isoformat()
        con.execute("UPDATE inventory SET updated_at=? WHERE sku='EL-003'", (stamp,))
        con.execute("UPDATE inventory SET updated_at=? WHERE sku='EL-003' AND location_id='ST-HN'",
                    ((datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),))
    result = c.post('/api/workflows/freshness/route', json={
        'metric': 'available_stock', 'sku': 'EL-003', 'requested_tier': '15_min',
    }).json()
    assert result['status'] == 'STALE' and not result['meets_target']


def test_freshness_route_api_selects_other_sources_but_does_not_fabricate_refresh(client):
    c, db = client
    for metric, expected in [
        ('net_revenue', 'hourly'), ('top_sellers', 'daily'),
        ('product_knowledge', 'daily'), ('order_state', 'live'),
    ]:
        response = c.post('/api/workflows/freshness/route', json={'metric': metric})
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['applied_tier'] == expected
        assert value['status'] == 'UNVERIFIED'
        assert value['execution_mode'] == 'route_only_no_source_timestamp'
        assert value['tool_execution'] == 'not_executed_by_router'


def test_freshness_route_api_rejects_dropped_sku_and_invalid_metric(client):
    c, db = client
    cases = [
        {'metric': 'available_stock'},
        {'metric': 'net_revenue', 'sku': 'EL-003'},
        {'metric': 'unknown'},
        {'metric': 'available_stock', 'sku': 'EL-003', 'requested_tier': 'weekly'},
    ]
    assert [c.post('/api/workflows/freshness/route', json=v).status_code for v in cases] == [422]*4


def test_existing_week2_workflow_uses_shared_evidence(client):
    c, db = client
    r = c.post('/api/workflows/run', json={'scenario':'week2', 'sku':'EL-003'})
    assert r.status_code == 200
    assert 'Target: 15 minutes; STALE' in r.json()['report']
    assert r.json()['graph']['execution'] == 'deterministic_local_simulation'

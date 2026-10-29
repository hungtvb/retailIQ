"""Synthetic four-week vertical workflows for the local RetailIQ course demo.

These are deterministic executions against reviewed SQLite reads, NOT live A2A,
real customer memory, real order placement, or authenticated RBAC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import closing
import json
import os
import sqlite3
import uuid

from retailiq.domain.analytics import catalog_product, inventory, revenue, top, month
from retailiq.observability import log_event

HCM = timezone(timedelta(hours=7))
GRAPH = {
    "week2": [
        ("request", "Question", "input"),
        ("inventory_mcp", "Inventory API", "tool"),
        ("semantic_layer", "KPI definitions", "guard"),
        ("freshness_guard", "Freshness check", "guard"),
        ("evidence", "Grounded answer", "output"),
    ],
    "week3": [
        ("request", "Price review", "input"),
        ("scope_guard", "Scope policy", "guard"),
        ("inventory_search_agent", "Inventory Agent", "agent"),
        ("dynamic_pricing_agent", "Pricing Agent", "agent"),
        ("verification", "Verify proposal", "guard"),
        ("manager_approval", "Manager review", "human"),
        ("finalize", "Record decision", "output"),
    ],
    "alerts": [
        ("request", "KPI monitoring", "input"),
        ("semantic_layer", "KPI definitions", "guard"),
        ("inventory_search_agent", "Inventory Agent", "agent"),
        ("kpi_alert", "Alert rule", "guard"),
        ("evidence", "Alert report", "output"),
    ],
    "week4": [
        ("request", "Order request", "input"),
        ("inventory_search_agent", "Inventory Agent", "agent"),
        ("fulfilment_optimisation_agent", "Fulfilment Agent", "agent"),
        ("customer_context_agent", "Customer Agent", "agent"),
        ("dynamic_pricing_agent", "Pricing Agent", "agent"),
        ("order_management_agent", "Order Agent", "agent"),
        ("verification", "Verification", "guard"),
        ("manager_approval", "Manager review", "human"),
        ("finalize", "Record decision", "output"),
    ],
}

DESCRIPTIONS = {
    "week2": "Week 2 · Freshness, semantic definitions and inventory read (local MCP-equivalent adapter)",
    "week3": "Week 3 · Governed pricing proposal with manager decision (simulated role)",
    "alerts": "Week 3 · Read-only KPI alert screening",
    "week4": "Week 4 · Five-agent A2A-style order proposal with verification and approval",
}


EDGE_LABELS = {
    "week2": ["query", "rows", "KPI", "timestamp"],
    "week3": ["scope", "stock", "proposal", "validate", "review", "decision"],
    "alerts": ["metrics", "query", "threshold", "report"],
    "week4": ["stock", "allocate", "context", "price", "draft", "verify", "approve", "record"],
}


def definitions() -> list[dict]:
    return [{"id": key, "title": DESCRIPTIONS[key],
             "nodes": [{"id": i, "label": title, "kind": kind} for i, title, kind in nodes],
             "edges": [{"from": nodes[n][0], "to": nodes[n + 1][0],
                        "label": EDGE_LABELS[key][n]}
                       for n in range(len(nodes) - 1)],
             "execution": "deterministic_local_simulation"} for key, nodes in GRAPH.items()]


def _db() -> Path:
    path = Path(os.environ.get("RETAILIQ_WORKFLOW_DB") or
                (Path(__file__).resolve().parents[2] / "data" / "workflow_demo.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect():
    connection = sqlite3.connect(_db(), timeout=3)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS workflow_runs (
      id TEXT PRIMARY KEY, scenario TEXT NOT NULL, status TEXT NOT NULL,
      trace_json TEXT NOT NULL, report TEXT NOT NULL,
      created_at TEXT NOT NULL, decision_at TEXT
    )""")
    return connection


def _save(scenario: str, status: str, events: list[dict], report: str) -> dict:
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as db:
        with db:
            db.execute("INSERT INTO workflow_runs VALUES (?,?,?,?,?,?,NULL)",
                       (run_id, scenario, status, json.dumps(events), report, now))
    return read_run(run_id)


def read_run(run_id: str) -> dict | None:
    with closing(_connect()) as db:
        record = db.execute(
            "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
    if record is None:
        return None
    result = dict(record)
    result["events"] = json.loads(result.pop("trace_json"))
    result["graph"] = next(d for d in definitions() if d["id"] == result["scenario"])
    result["simulation_notice"] = ("Local synthetic simulation; demo role is not "
                                  "authentication; no product price, inventory or sales order is mutated.")
    return result


def review_run(run_id: str, role: str, decision: str) -> dict:
    if role != "manager":
        raise PermissionError("Only the simulated manager role may review proposals")
    if decision not in ("approve", "reject"):
        raise ValueError("Review must be approve or reject")
    with closing(_connect()) as db:
        with db:
            row = db.execute("SELECT status,trace_json,scenario FROM workflow_runs WHERE id=?",
                             (run_id,)).fetchone()
            if row is None:
                raise KeyError("Workflow run not found")
            if row["status"] != "pending_manager":
                raise ValueError("Workflow is not pending manager review")
            events = json.loads(row["trace_json"])
            outcome = "approved_simulated" if decision == "approve" else "rejected"
            events.append({"node": "manager_approval", "status": "completed",
                           "detail": "Manager " + decision + "d proposal (simulated)"})
            events.append({"node": "finalize", "status": "completed",
                           "detail": "Decision recorded; no operational data changed"})
            changed = db.execute(
                "UPDATE workflow_runs SET status=?,trace_json=?,decision_at=? "
                "WHERE id=? AND status='pending_manager'",
                (outcome, json.dumps(events), datetime.now(timezone.utc).isoformat(), run_id))
            if changed.rowcount != 1:
                raise ValueError("Workflow review conflict")
    log_event("workflow.review.completed", agent="manager_approval",
              status=outcome, execution_mode="offline")
    return read_run(run_id)


def _freshness(rows: list[dict]) -> dict:
    updates = [datetime.fromisoformat(row["updated_at"]) for row in rows]
    newest = max(updates) if updates else None
    # Compared to actual time; old synthetic inventory must never be called live.
    age = int((datetime.now(timezone.utc) - newest.astimezone(timezone.utc)).total_seconds()) if newest else None
    return {"tier": "15 minutes", "observed_at": newest.isoformat() if newest else None,
            "age_seconds": age, "meets_target": bool(age is not None and 0 <= age <= 900)}


def run_demo(scenario: str, sku: str, quantity: int = 1,
             role: str = "analyst") -> dict:
    if scenario not in GRAPH:
        raise ValueError("Unknown scenario")
    if role not in ("analyst", "manager"):
        raise ValueError("Unknown simulated role")
    if type(quantity) is not int or not 1 <= quantity <= 20:
        raise ValueError("Quantity must be an integer from 1 to 20")
    product = catalog_product(sku)
    if product is None:
        raise ValueError("Product SKU is not in the synthetic catalog")
    stock = inventory(product["sku"])
    available = sum(row["available"] for row in stock)
    events: list[dict] = []
    previous = None

    def step(node, detail, status="completed"):
        nonlocal previous
        if previous is not None:
            log_event("agent.handoff", previous_agent=previous, target_agent=node,
                      execution_mode="offline")
        events.append({"node": node, "status": status, "detail": str(detail)[:180],
                       "from": previous})
        log_event("workflow.node.completed", agent=node, status=status, execution_mode="offline")
        previous = node

    step("request", "Synthetic scenario: " + scenario)
    if scenario == "week2":
        step("inventory_mcp", "Local read adapter for " + product["sku"] +
             "; MCP network transport not exercised")
        step("semantic_layer", "Available = on_hand - reserved; revenue uses completed orders; "
             "top sellers rank completed units")
        freshness = _freshness(stock)
        step("freshness_guard", "Inventory snapshot " + ("meets" if freshness["meets_target"]
             else "does not meet") + " the 15-minute target")
        step("evidence", str(available) + " available units from " + str(len(stock)) +
             " locations; source timestamps retained")
        report = ("Stock: " + str(available) + " available for " + product["sku"] +
                  ". Source timestamp: " + str(freshness["observed_at"]) +
                  ". Target: 15 minutes; " +
                  ("PASS" if freshness["meets_target"] else "STALE") +
                  ". Not real-time data. Completed-order revenue (month " +
                  month() + "): " + str(sum(x["net_revenue_vnd"] for x in revenue())) +
                  " VND. Top sellers: " + ", ".join(x["sku"] for x in top()) + ".")
        status = "completed"
    elif scenario == "alerts":
        step("semantic_layer", "Alert on available quantity below 20 units")
        step("inventory_search_agent", "Reviewed SQL inventory: " + str(available) + " units")
        alert = available < 20
        step("kpi_alert", "Low-stock screening: " + ("ALERT" if alert else "NORMAL"))
        step("evidence", "No notifications sent; read-only alert evaluation")
        report = ("Low-stock KPI: " + ("ALERT" if alert else "NORMAL") +
                  ". Available units for " + product["sku"] + ": " + str(available) +
                  ". Threshold: 20. Local sample, not monitoring or an external notification.")
        status = "completed"
    elif scenario == "week3":
        step("scope_guard", "Catalog-only pricing proposal; actor is a simulated " + role)
        step("inventory_search_agent", str(available) + " units from verified stock records")
        proposal_price = product["price_vnd"] * 95 // 100
        step("dynamic_pricing_agent", "Propose 5% markdown; rounded proposal " +
             str(proposal_price) + " VND")
        step("verification", "No write tool exposed; proposal checked against catalog price")
        step("manager_approval", "Manager decision required", "awaiting")
        report = ("Pricing PROPOSAL only for " + product["sku"] + ": " +
                  str(product["price_vnd"]) + " → " + str(proposal_price) +
                  " VND (illustrative 5% reduction). Manager approval pending. "
                  "A decision will not change the catalog.")
        status = "pending_manager"
    else:
        step("inventory_search_agent", str(available) + " units available across locations")
        eligible = [row for row in stock if row["available"] >= quantity]
        location = min(eligible, key=lambda x: (-x["available"], x["location_id"])) if eligible else None
        step("fulfilment_optimisation_agent",
             "Single-location allocation: " + location["location_id"] if location
             else "No single location can fulfil requested quantity")
        step("customer_context_agent", "Anonymous synthetic guest; no profile lookup or PII")
        step("dynamic_pricing_agent", "Read-only list price " + str(product["price_vnd"]) + " VND")
        step("order_management_agent", "Draft " + str(quantity) + " × " + product["sku"] +
             "; no order inserted")
        valid = location is not None and available >= quantity
        step("verification", "Allocation, SKU, quantity and price " +
             ("verified" if valid else "failed"), "completed" if valid else "blocked")
        if valid:
            step("manager_approval", "Manager decision required", "awaiting")
            report = ("Draft order for " + str(quantity) + " × " + product["sku"] +
                      "; location " + location["location_id"] +
                      "; list total " + str(quantity * product["price_vnd"]) +
                      " VND. Verified against synthetic snapshot; manager review pending. "
                      "No real sales order or reservation.")
            status = "pending_manager"
        else:
            report = ("Order proposal BLOCKED: no single location has " + str(quantity) +
                      " units of " + product["sku"] + ". No order was created.")
            status = "blocked"
    return _save(scenario, status, events, report)

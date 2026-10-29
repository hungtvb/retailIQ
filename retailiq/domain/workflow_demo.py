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
from retailiq.domain.semantic import semantic_summary, FRESHNESS_TIERS
from retailiq.observability import log_event

HCM = timezone(timedelta(hours=7))
GRAPH = {
    "week1": [
        ("request", "Retail question", "input"),
        ("router", "Intent router", "guard"),
        ("sales_agent", "Sales Agent", "agent"),
        ("sql_tool", "Reviewed SQL", "tool"),
        ("evidence", "SQL evidence", "guard"),
        ("answer", "Grounded answer", "output"),
    ],
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
    "week1": "Week 1 · Stock/Sales SQL query preview (for live LangGraph use Assistant)",
    "week2": "Week 2 · Freshness, semantic definitions and inventory read (local MCP-equivalent adapter)",
    "week3": "Week 3 · Governed pricing proposal with manager decision (simulated role)",
    "alerts": "Week 3 · Read-only KPI alert screening",
    "week4": "Week 4 · Five-agent A2A-style order proposal with verification and approval",
}


EDGE_LABELS = {
    "week1": ["route", "delegate", "query", "rows", "answer"],
    "week2": ["query", "rows", "KPI", "timestamp"],
    "week3": ["scope", "stock", "proposal", "validate", "review", "decision"],
    "alerts": ["metrics", "query", "threshold", "report"],
    "week4": ["stock", "allocate", "context", "price", "draft", "verify", "approve", "record"],
}


def definitions() -> list[dict]:
    return [{"id": key, "title": DESCRIPTIONS[key],
             "nodes": [{"id": i, "label": title, "kind": kind} for i, title, kind in nodes],
             "edges": ([{"from": nodes[n][0], "to": nodes[n + 1][0],
                          "label": EDGE_LABELS[key][n]}
                         for n in range(len(nodes) - 1)] +
                       ([{"from": "verification", "to": "fulfilment_optimisation_agent",
                          "label": "retry"},
                         {"from": "fulfilment_optimisation_agent",
                          "to": "order_management_agent", "label": "revise"}]
                        if key == "week4" else [])),
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
            row = db.execute("SELECT status,trace_json,scenario,report FROM workflow_runs WHERE id=?",
                             (run_id,)).fetchone()
            if row is None:
                raise KeyError("Workflow run not found")
            if row["status"] != "pending_manager":
                raise ValueError("Workflow is not pending manager review")
            events = json.loads(row["trace_json"])
            outcome = "approved_simulated" if decision == "approve" else "rejected"
            events.append({"node": "manager_approval", "status": "completed",
                           "from": events[-1].get("from"),
                           "detail": "Manager " + decision + "d proposal (simulated)"})
            events.append({"node": "finalize", "status": "completed",
                           "from": "manager_approval",
                           "detail": "Decision recorded; no operational data changed"})
            report = (row["report"]
                      .replace("Manager approval pending.", "")
                      .replace("manager review pending.", "").rstrip() +
                      " Manager decision: " + outcome +
                      ". This is a recorded simulation, not a catalog or order mutation.")
            changed = db.execute(
                "UPDATE workflow_runs SET status=?,trace_json=?,report=?,decision_at=? "
                "WHERE id=? AND status='pending_manager'",
                (outcome, json.dumps(events), report,
                 datetime.now(timezone.utc).isoformat(), run_id))
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
            "age_seconds": age, "meets_target": bool(age is not None and 0 <= age <= FRESHNESS_TIERS["15_min"]["target_seconds"])}


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
            event_name = ("agent.handoff" if previous.endswith("_agent") and
                          node.endswith("_agent") else "workflow.handoff")
            log_event(event_name, previous_agent=previous, target_agent=node,
                      execution_mode="offline")
        events.append({"node": node, "status": status, "detail": str(detail)[:180],
                       "from": previous})
        log_event("workflow.node.updated" if status in ("running", "awaiting") else
                  "workflow.node.completed", agent=node, status=status,
                  execution_mode="offline")
        previous = node

    step("request", "Synthetic scenario: " + scenario)
    if scenario == "week1":
        step("router", "Top-seller intent selected for synthetic sales query")
        step("sales_agent", "Sales specialist is responsible for completed orders")
        leaders = top()
        step("sql_tool", "Reviewed parameterized completed-order SQL returned " +
             str(len(leaders)) + " rows")
        step("evidence", "Product SKUs and completed-order units are grounded in SQLite")
        step("answer", "Verified top-seller report from source records")
        report = ("Week 1 SQL preview: " +
                  "; ".join(row["sku"] + ": " + str(row["units_sold"]) +
                            " units" for row in leaders) +
                  ". Deterministic preview, not live LangGraph. "
                  "Use the Assistant tab for live SSE / full-mode LangGraph.")
        status = "completed"
    elif scenario == "week2":
        if os.getenv("RETAILIQ_WORKFLOW_USE_MCP", "0") == "1":
            from retailiq.mcp_adapter import read_inventory
            mcp_stock = read_inventory(product["sku"])
            if mcp_stock != stock:
                raise ValueError("MCP stock evidence differs from reviewed SQL")
            stock = mcp_stock
            available = sum(row["available"] for row in stock)
            step("inventory_mcp", "Real stdio MCP inventory tool invoked via LangChain adapter")
        else:
            step("inventory_mcp", "Local read adapter for " + product["sku"] +
                 "; MCP network transport not exercised")
        step("semantic_layer", semantic_summary())
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
        # Demonstrate row filtering in a policy slice; the role field is NOT
        # authenticated and must never be presented as real RBAC.
        scoped_stock = stock if role == "manager" else [
            row for row in stock if row["location_id"] == "ST-HCM"]
        scoped_available = sum(row["available"] for row in scoped_stock)
        step("scope_guard", "Simulated " + role + " scope: " +
             ("all locations" if role == "manager" else "ST-HCM only"))
        step("inventory_search_agent", str(scoped_available) +
             " visible units from " + str(len(scoped_stock)) + " permitted locations")
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
        allocation_label = location["location_id"] if location else "none"
        if valid:
            step("verification", "Single-location allocation, SKU, quantity and price verified")
        elif available >= quantity:
            # One bounded verification → replan → verification loop.
            # This is a proposal only; no reservations are made.
            step("verification", "Single-location plan failed; request bounded replan", "running")
            remaining = quantity
            legs = []
            for row in sorted(stock, key=lambda item: (-item["available"], item["location_id"])):
                take = min(remaining, row["available"])
                if take:
                    legs.append((row["location_id"], take))
                    remaining -= take
                if remaining == 0:
                    break
            valid = remaining == 0
            allocation_label = ", ".join(code + ": " + str(count) for code, count in legs)
            step("fulfilment_optimisation_agent", "Replanned split allocation: " + allocation_label)
            step("order_management_agent", "Revised draft after verification feedback")
            step("verification", "Split allocation " + ("verified" if valid else "failed"),
                 "completed" if valid else "blocked")
        else:
            step("verification", "Insufficient total inventory", "blocked")
        if valid:
            step("manager_approval", "Manager decision required", "awaiting")
            report = ("Draft order for " + str(quantity) + " × " + product["sku"] +
                      "; allocation " + allocation_label +
                      "; list total " + str(quantity * product["price_vnd"]) +
                      " VND. Verified against synthetic snapshot; manager review pending. "
                      "No real sales order or reservation.")
            status = "pending_manager"
        else:
            report = ("Order proposal BLOCKED: insufficient verified stock for " +
                      str(quantity) + " units of " + product["sku"] +
                      ". No order was created.")
            status = "blocked"
    return _save(scenario, status, events, report)

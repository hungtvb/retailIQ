"""UC-01 read-only backorder investigation over verified Fiction business facts.

The policy is resolved by exact identity and document checksum, never an LLM
guess or semantic search. This is M1 domain logic, not an Agent or approval.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from retailiq.domain.fiction import (
    FictionDataError, FictionStore, RELEASE, _aware_timestamp,
)

_POLICY_ID = "FR-WH-2026-10-04"
_POLICY_PATH = "policies/FR-WH-2026-10-04.md"
_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_POLICY_START = datetime(2026, 10, 4, tzinfo=_TZ)
_POLICY_END = datetime(2026, 11, 3, tzinfo=_TZ)
_POLICY_HEADER = b"**Policy reference:** FR-WH-2026-10-04"
_POLICY_EFFECTIVE = "**Effective:** 4 October 2026 – 2 November 2026"


def _effective_warehouse_policy(
    store: FictionStore, knowledge_root: str | Path, cutoff: str,
) -> tuple[dict | None, str | None]:
    """Resolve one release-pinned warehouse policy; return nonfatal coverage gap."""
    if store.release["pack_version"] != RELEASE:
        raise FictionDataError("Unsupported policy release")

    policies = store._q(  # SQL is fixed and parameterized, never model-generated.
        "SELECT policy_id, requires_manager_approval FROM fulfillment_policies "
        "WHERE policy_id=?", (_POLICY_ID,),
    )
    if len(policies) != 1:
        return None, "POLICY_REGISTRY_MISSING"
    if policies[0]["requires_manager_approval"] != 1:
        raise FictionDataError("Warehouse policy approval authority mismatch")

    docs = store._q(
        "SELECT document_id, relative_path, sha256 FROM knowledge_documents "
        "WHERE policy_id=? AND kind='business_policy'", (_POLICY_ID,),
    )
    if len(docs) != 1:
        return None, "POLICY_DOCUMENT_REGISTRY_MISSING"
    doc = docs[0]
    # Exact path is a reviewed source contract and prevents traversal.
    if doc["relative_path"] != _POLICY_PATH:
        raise FictionDataError("Warehouse policy source path mismatch")

    root = Path(knowledge_root).resolve()
    path = (root / _POLICY_PATH).resolve()
    if not path.is_relative_to(root):
        raise FictionDataError("Warehouse policy source escaped the knowledge root")
    try:
        original = path.read_bytes()
    except FileNotFoundError:
        return None, "POLICY_DOCUMENT_MISSING"
    except OSError as exc:
        raise FictionDataError("Warehouse policy source cannot be read") from exc
    if sha256(original).hexdigest() != doc["sha256"]:
        raise FictionDataError("Warehouse policy document SHA-256 mismatch")
    if _POLICY_HEADER not in original or _POLICY_EFFECTIVE.encode("utf-8") not in original:
        raise FictionDataError("Warehouse policy identity/validity statement mismatch")

    effective = _POLICY_START <= _aware_timestamp(cutoff).astimezone(_TZ) < _POLICY_END
    return {
        "policy_id": _POLICY_ID,
        "document_id": doc["document_id"],
        "relative_path": doc["relative_path"],
        "sha256": doc["sha256"],
        "source_release": store.release["pack_version"],
        "effective_from": _POLICY_START.isoformat(),
        "effective_to_exclusive": _POLICY_END.isoformat(),
        "applicable_at_cutoff": effective,
        "requires_manager_approval": True,
    }, None if effective else "POLICY_NOT_EFFECTIVE_AT_CUTOFF"


def investigate_backorder(
    store: FictionStore, case_id: str, *, knowledge_root: str | Path,
) -> dict:
    """Return source-grounded UC-01 findings, with no transfer/stock mutation.

    Status is for the bounded *requested finding*. A supported negative means
    only that evaluated case-recorded alternatives yielded no candidate.
    """
    case_evidence = store.fulfillment_case(case_id)
    if case_evidence["data"] is None:
        raise FictionDataError("CASE_NOT_FOUND")
    case = case_evidence["data"]["case"]
    cutoff = case_evidence["data"]["cutoff"]
    order_evidence = store.order(case["order_id"])
    order = order_evidence["data"]
    if not order:
        raise FictionDataError("Case has no matching order")
    lines = [line for line in order["lines"] if line["order_item_id"] == case["order_item_id"]]
    if (len(lines) != 1 or lines[0]["product_id"] != case["product_id"]
            or type(lines[0]["quantity"]) is not int
            or not 0 < case["request_qty"] <= lines[0]["quantity"]):
        raise FictionDataError("Case/order item/product/quantity mismatch")

    policy, policy_reason = _effective_warehouse_policy(store, knowledge_root, cutoff)
    evidence = case_evidence["data"]
    candidates = evidence["evidence_candidates"]
    routes = [
        route for route in evidence["warehouse_eligibility"]
        if route["warehouse_id"] != case["assigned_warehouse_id"]
    ]
    reasons: set[str] = set()
    if policy_reason:
        reasons.add(policy_reason)
    if not routes:
        reasons.add("NO_ALTERNATIVE_ROUTE_RECORD")
    if not evidence["snapshots"]:
        reasons.add("NO_CASE_SNAPSHOT")

    # Require usable stock evidence for every *eligible recorded alternative*.
    # A denied route itself is sufficient to exclude that recorded warehouse.
    cutoff_dt = _aware_timestamp(cutoff)
    for route in routes:
        if route["eligible"] != 1:
            continue
        observed = [
            snap for snap in evidence["snapshots"]
            if (snap["warehouse_id"] == route["warehouse_id"]
                and snap["product_id"] == case["product_id"]
                and _aware_timestamp(snap["observed_at"]) <= cutoff_dt
                and _aware_timestamp(snap["received_at"]) <= cutoff_dt
                and (cutoff_dt - _aware_timestamp(snap["observed_at"])).total_seconds() <= 86400)
        ]
        if not observed:
            reasons.add("NO_USABLE_SNAPSHOT_FOR_ELIGIBLE_ROUTE")
    recorded_ids = {route["warehouse_id"] for route in routes}
    if any(
        snap["warehouse_id"] != case["assigned_warehouse_id"]
        and snap["warehouse_id"] not in recorded_ids
        for snap in evidence["snapshots"]
    ):
        reasons.add("WAREHOUSE_ROUTE_UNKNOWN")

    unverified = bool(reasons)
    if unverified:
        disposition = "INSUFFICIENT_EVIDENCE"
    elif candidates:
        disposition = "NEEDS_REVIEW"  # Candidate proposal, never an approval.
    else:
        disposition = "SUPPORTED"  # Only the recorded/evaluated negative finding.

    refs = list(dict.fromkeys(case_evidence["record_refs"] + order_evidence["record_refs"]))
    if policy is not None:
        refs.extend([
            f"fulfillment_policies/{policy['policy_id']}",
            f"knowledge_documents/{policy['document_id']}",
        ])
    return {
        "data": {
            "case": case,
            "cutoff": cutoff,
            "evidence_candidates": candidates,
            "snapshots": evidence["snapshots"],
            "warehouse_eligibility": evidence["warehouse_eligibility"],
            "policy": policy,
        },
        "disposition": disposition,
        "approval_status": "NOT_REQUESTED",
        "reason_codes": sorted(reasons),
        "source": case_evidence["source"],
        "scope": {
            **case_evidence["scope"],
            "finding_scope": "recorded_case_alternative_warehouses_only",
        },
        "record_refs": refs,
        "temporal": case_evidence["temporal"],
        "limitations": case_evidence["limitations"]
        + ["Historical case evidence does not prove current or company-wide inventory"],
    }
}

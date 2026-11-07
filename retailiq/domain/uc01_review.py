"""Canonical historical UC-01 review candidate; no model, graph or write authority."""
from __future__ import annotations

from pathlib import Path

from retailiq.domain.backorder import investigate_backorder
from retailiq.domain.fiction import FictionDataError, FictionStore


def verified_candidate(
    store: FictionStore,
    knowledge_root: Path,
    case_binding: dict,
    candidate_snapshot_id: str | None = None,
) -> dict:
    """Recompute a candidate at the case's ORIGINAL cutoff from pinned Fiction.

    The binding is a previously persisted assistant-tool result, not a source of
    eligibility. Never trust LLM text, request-supplied source or live stock.
    """
    if (not isinstance(case_binding, dict)
            or case_binding.get("version") != 1
            or case_binding.get("disposition") != "NEEDS_REVIEW"
            or case_binding.get("source_id") != "fiction-retail/sqlite"
            or case_binding.get("source_version") != store.release["pack_version"]
            or case_binding.get("source_sha256") != store.release["runtime_sha256"]):
        raise FictionDataError("Case source or review state is not verified")
    case_id = case_binding.get("case_id")
    if (not isinstance(case_id, str)
            or case_binding.get("case_ref") != f"fulfillment_cases/{case_id}"):
        raise FictionDataError("Case identity is not verified")
    result = investigate_backorder(store, case_id, knowledge_root=knowledge_root)
    if (result["source"]["id"] != case_binding["source_id"]
            or result["source"]["version"] != case_binding["source_version"]
            or result["source"]["sha256"] != case_binding["source_sha256"]
            or result["data"]["cutoff"] != case_binding.get("cutoff")
            or result["temporal"].get("evidence_cutoff") != case_binding["cutoff"]):
        raise FictionDataError("Original historical source or cutoff changed")
    if (result["disposition"] != "NEEDS_REVIEW"
            or result["approval_status"] != "NOT_REQUESTED"):
        raise ValueError("Historical finding is not eligible for approval proposal")
    policy = result["data"]["policy"]
    if (not isinstance(policy, dict)
            or policy.get("applicable_at_cutoff") is not True
            or policy.get("requires_manager_approval") is not True
            or "POLICY_CONFLICT" in result["reason_codes"]):
        raise ValueError("Effective, non-conflicting policy is required")
    candidates = result["data"]["evidence_candidates"]
    if not candidates:
        raise ValueError("No verified alternative warehouse candidate")
    if candidate_snapshot_id is None:
        if len(candidates) != 1:
            raise ValueError("Multiple candidates require an explicit snapshot selector")
        selected = candidates[0]
    else:
        matches = [c for c in candidates
                   if c.get("snapshot_id") == candidate_snapshot_id]
        if len(matches) != 1:
            raise ValueError("Candidate snapshot is not eligible or is ambiguous")
        selected = matches[0]
    case = result["data"]["case"]
    snapshots = [s for s in result["data"]["snapshots"]
                 if s["snapshot_id"] == selected["snapshot_id"]]
    routes = [r for r in result["data"]["warehouse_eligibility"]
              if r["warehouse_id"] == selected["warehouse_id"]]
    if (len(snapshots) != 1 or len(routes) != 1 or routes[0]["eligible"] != 1
            or selected["warehouse_id"] == case["assigned_warehouse_id"]
            or snapshots[0]["product_id"] != case["product_id"]
            or snapshots[0]["warehouse_id"] != selected["warehouse_id"]
            or snapshots[0]["candidate_eligible"] is not True
            or selected["available_at_observation"] !=
                snapshots[0]["available_at_observation"]
            or type(case["request_qty"]) is not int
            or type(selected["available_at_observation"]) is not int
            or selected["available_at_observation"] < case["request_qty"]):
        raise FictionDataError("Candidate snapshot, quantity or route is inconsistent")

    return {
        "case_id": case_id,
        "order_id": case["order_id"],
        "order_item_id": case["order_item_id"],
        "product_id": case["product_id"],
        "source_id": result["source"]["id"],
        "source_version": result["source"]["version"],
        "source_sha256": result["source"]["sha256"],
        "cutoff": result["data"]["cutoff"],
        "policy_id": policy["policy_id"],
        "policy_document_id": policy["document_id"],
        "policy_sha256": policy["sha256"],
        "warehouse_id": selected["warehouse_id"],
        "snapshot_id": selected["snapshot_id"],
        "requested_units": case["request_qty"],
        "available_units": selected["available_at_observation"],
        # Bounded verified references; never store chat, raw documents or customer data.
        "evidence_refs": list(dict.fromkeys(result["record_refs"]))[:100],
        # Request IDs identify chat turns, not historical business candidates.
        "finding_disposition": "NEEDS_REVIEW",
        "finding_approval_status": "NOT_REQUESTED",
    }

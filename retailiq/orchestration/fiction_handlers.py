"""Fiction evidence-to-response composition for existing graph node wrappers.

No graph ownership, model, legacy analytics, SQL construction or policy
applicability decisions live here. The caller supplies source-verified facts
and a lazy read-only Order MCP callback for the one opt-in follow-up path.
"""
from __future__ import annotations

from typing import Callable

from retailiq.language import is_vietnamese
from retailiq.orchestration.fiction_requests import UnresolvedCaseReference


def inventory_update(state: dict, result: dict) -> dict:
    """Describe source-verified but temporally undated inventory as undated."""
    product = state["fiction_product"]
    rows = result["data"]
    limits = result["limitations"]
    vi = is_vietnamese(state["question"])
    if not rows:
        reason = (limits[-1] if limits else "NO_INVENTORY_RECORDS")
        answer = (f"Không có bằng chứng tồn kho xác thực cho {product}: {reason}. "
                  "Không thể suy ra số lượng bằng 0."
                  if vi else f"No verified inventory rows for {product}: {reason}. "
                  "Missing evidence is not zero.")
    else:
        details = "; ".join(
            f"{r['warehouse_id']}: {r['available_snapshot']}" for r in rows
        )
        answer = (f"Bản ghi tồn kho không có thời điểm quan sát cho {product}: {details}. "
                  "Đây KHÔNG phải tồn kho hiện tại hoặc tại một thời điểm lịch sử."
                  if vi else
                  f"Undated recorded stock for {product}: {details}. "
                  "This does NOT prove current or historical stock.")
    return {
        "intent": "fiction_stock", "answer": answer, "active_agent": "fiction_inventory_agent",
        "records": rows, "contexts": [], "source": result["source"],
        "evidence_refs": result["record_refs"], "limitations": limits,
        "temporal": result["temporal"], "approval_status": None,
    }


def backorder_update(
    state: dict,
    investigation: dict,
    case_id: str,
    *,
    followup: str | None,
    committed: dict | None,
    read_order: Callable[[str], dict],
    capability: str,
    policy_explanation: dict | None = None,
) -> dict:
    """Compose findings from already verified facts; no new policy decisions."""
    data = investigation['data']
    candidates = data['evidence_candidates']
    cutoff = data['cutoff']
    reasons = investigation['reason_codes']
    disposition = investigation['disposition']
    vi = is_vietnamese(state['question'])
    snapshots = {s['snapshot_id']: s for s in data['snapshots']}
    records = [
        {'case_id': case_id, 'cutoff': cutoff, 'snapshot_id': item['snapshot_id'],
         'warehouse_id': item['warehouse_id'],
         'observed_at': snapshots[item['snapshot_id']]['observed_at'],
         'received_at': snapshots[item['snapshot_id']]['received_at'],
         'available_at_observation': item['available_at_observation']}
        for item in candidates
    ]
    if followup == 'order_status_at_cutoff':
        disposition = 'INSUFFICIENT_EVIDENCE'
        reasons = sorted(set(reasons) | {'ORDER_STATUS_AT_CUTOFF_UNVERIFIED'})
        answer = ('Không có lịch sử trạng thái đơn/giao hàng được xác minh tại cutoff '
                  f'{cutoff}; trạng thái ghi trong bản phát hành không chứng minh trạng thái lúc đó.'
                  if vi else
                  f'Order/shipment status at case cutoff {cutoff} is unverified; '
                  'release-recorded status cannot be treated as historical status.')
    elif followup == 'order_details':
        case = data['case']
        order_detail = read_order(case['order_id'])
        o = order_detail['data']
        if (order_detail['source'] != investigation['source'] or
                order_detail['scope'].get('order_id') != case['order_id'] or
                not isinstance(o, dict) or
                len([line for line in o['lines'] if
                     line['order_item_id'] == case['order_item_id'] and
                     line['product_id'] == case['product_id'] and
                     line['quantity'] >= case['request_qty']]) != 1):
            raise UnresolvedCaseReference('Order/case identity or source changed')
        items = '; '.join(f"{line['product_id']}: {line['quantity']}" for line in o['lines'])
        answer = (f"Đơn {case['order_id']} gồm: {items}. Đây là dữ liệu đơn hàng tại bản phát hành; "
                  "trạng thái giao hàng KHÔNG phải trạng thái tại cutoff lịch sử."
                  if vi else
                  f"Order {case['order_id']} lines: {items}. Release-recorded shipment/order "
                  "state is NOT a historical state at the backorder cutoff.")
    elif followup == 'policy' and data['policy'] and data['policy']['applicable_at_cutoff']:
        policy = data['policy']
        answer = (f"Case {case_id} tại {cutoff}: chính sách {policy['policy_id']} có hiệu lực "
                  "và yêu cầu Manager phê duyệt đề xuất chuyển kho; chưa có chuyển kho nào được thực hiện."
                  if vi else
                  f"Case {case_id} at {cutoff}: policy {policy['policy_id']} applies and "
                  "requires Manager review for a transfer proposal; no transfer has occurred.")
    elif 'POLICY_CONFLICT' in reasons:
        answer = (f'Case {case_id} tại {cutoff}: các chính sách kho mâu thuẫn; cần xác minh quyền áp dụng. '
                  'Không có đề xuất chuyển kho được phê duyệt.'
                  if vi else
                  f'Case {case_id} at {cutoff}: warehouse policy authority conflicts. '
                  'Policy review is required; no transfer is approved.')
    elif disposition == 'NEEDS_REVIEW':
        details = '; '.join(
            f"{x['warehouse_id']} ({x['available_at_observation']})" for x in candidates[:5]
        )
        answer = (f'Case {case_id} tại {cutoff}: kho thay thế có bằng chứng đủ điều kiện: {details}. '
                  'Đây chỉ là đề xuất, cần Manager phê duyệt; không phải tồn kho hiện tại.'
                  if vi else
                  f'Case {case_id} at {cutoff}: case-evidenced alternative warehouse candidates: {details}. '
                  'Manager review is required; this is not current stock or an approved transfer.')
    elif disposition == 'SUPPORTED':
        answer = (f'Case {case_id} tại {cutoff}: không có ứng viên hợp lệ trong các kho thay thế '
                  'đã được ghi nhận và đánh giá. Không thể suy ra toàn bộ kho của doanh nghiệp hết hàng.'
                  if vi else
                  f'Case {case_id} at {cutoff}: no eligible alternative among evaluated case-recorded '
                  'warehouses. This does not prove company-wide unavailability.')
    else:
        answer = (f'Case {case_id} tại {cutoff}: chưa đủ bằng chứng để kết luận khả năng chuyển kho. '
                  f'Thiếu/hạn chế: {", ".join(reasons)}. Không được suy ra tồn kho bằng 0.'
                  if vi else
                  f'Case {case_id} at {cutoff}: insufficient transfer evidence ({", ".join(reasons)}). '
                  'Missing evidence is not zero available inventory.')

    evidence_refs = investigation['record_refs'][:100]
    # Case/stock findings remain usable even if a policy document is missing
    # or in conflict; only attach policy lineage when its applicability passed.
    policy_ref = ([f"knowledge_documents/{data['policy']['document_id']}"]
                  if data['policy'] and data['policy']['applicable_at_cutoff'] else [])
    findings = [
        {'text': f"Alternative warehouse {r['warehouse_id']}: "
                 f"{r['available_at_observation']} units in observation at {r['observed_at']}, "
                 f"received at {r['received_at']}; verified evidence at cutoff {cutoff}",
         'evidence_refs': [f"inventory_snapshots_v2/{r['snapshot_id']}",
                           f"warehouse_eligibility/{case_id}/{r['warehouse_id']}"] + policy_ref}
        for r in records
    ]
    if followup == 'order_status_at_cutoff':
        findings = [{'text': 'Order/shipment status at case cutoff is not proven',
                     'evidence_refs': [f"fulfillment_cases/{case_id}"]}]
    if followup == 'order_details':
        evidence_refs = list(dict.fromkeys(evidence_refs + order_detail["record_refs"]))[:100]
        records = [dict(line) for line in order_detail["data"]["lines"]]
        findings = [{
            "text": ("Order lines recorded in the Fiction release; "
                     "shipment/order state not verified at case cutoff"),
            "evidence_refs": order_detail["record_refs"][:20],
        }]
    if followup == 'policy' and policy_ref:
        findings = [{
            'text': f"Warehouse policy {data['policy']['policy_id']} applies at {cutoff}; "
                    "Manager approval required for a proposed transfer",
            'evidence_refs': [
                f"fulfillment_policies/{data['policy']['policy_id']}", *policy_ref],
        }]
    if not findings:
        findings = [{'text': 'No eligible alternative in evaluated case records'
                     if disposition == 'SUPPORTED' else 'Transfer feasibility is not verified',
                     'evidence_refs': evidence_refs[:20]}]

    base = {
        'answer': answer, 'records': records, 'contexts': [],
        'active_agent': 'backorder_agent',
        'disposition': disposition, 'evidence_refs': evidence_refs,
        'findings': findings, 'limitations': investigation['limitations'] +
                       (['ORDER_STATUS_AT_CUTOFF_UNVERIFIED'] if followup == 'order_status_at_cutoff' else []),
        'approval_status': investigation['approval_status'],
        'reason_codes': reasons, 'source': investigation['source'],
        'temporal': investigation['temporal'],
        'capability_plan': {'kind': 'fixed_uc01',
                            'capabilities': ([capability, 'mcp.order_lookup']
                                             if followup == 'order_details' else [capability]),
                            'case_id': case_id,
                            'source': ('committed_session_case' if followup
                                       else 'validated_explicit_case_id'),
                            'source_request_id': committed.get('source_request_id') if followup else None},
    }

    # Policy explanation is optional, strictly subordinate to the verified
    # business investigation. It never changes authority or approval status.
    if followup == 'policy':
        if policy_explanation is not None and policy_ref:
            base['answer'] += '\n\n' + policy_explanation['answer']
            base['contexts'] = [policy_explanation['context']]
            ref = policy_explanation['evidence_ref']
            base['evidence_refs'] = list(dict.fromkeys(base['evidence_refs'] + [ref]))[:100]
            base['findings'].append({
                'text': f"Verified source clause: {policy_explanation['section']}",
                'evidence_refs': [ref],
            })
        else:
            base['limitations'] = list(dict.fromkeys(
                base['limitations'] + ['POLICY_EXPLANATION_UNVERIFIED']
            ))
    return base

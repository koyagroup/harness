"""Reviewer-facing decision history — a READ view over the append-only audit log.

Phase 4 writes two append-only rows per settlement decision (`settlement_decision_sent` +
`settlement_decision_response`, sharing a `harness_request_id`). This pairs them into one
logical record per decision and returns the compliance trail: what was approved/rejected, by
whom, when, the hold reason, and the resulting_state Koya returned.

Boundary: READ-ONLY — no actions, no money path. Gated to compliance / System Manager (it is
compliance data; ops can read raw system events via the audit list, not this trail). The audit
is VALUE-FREE by design (reason_present/reason_len, never the raw reason text, amounts, or PII);
this view surfaces only what's stored and never fabricates it.
"""

import json

import frappe

from harness.koya_harness import decision_render
from harness.koya_harness.api.settlement import can_send_decisions

_AUDIT = "Koya Harness Audit Log"
_SENT = "settlement_decision_sent"
_RESPONSE = "settlement_decision_response"


def _loads(raw) -> dict:
	"""Defensive parse of the stored detail_json text — tolerate null / invalid / non-dict."""
	if not raw:
		return {}
	try:
		data = json.loads(raw)
	except ValueError, TypeError:
		return {}
	return data if isinstance(data, dict) else {}


def _matches(record: dict, filters: dict) -> bool:
	"""Apply the optional filters to a paired record. All filters are optional; absent → match."""
	if not filters:
		return True
	if filters.get("decision") and record["decision"] != filters["decision"]:
		return False
	if filters.get("hold_reason") and record["hold_reason"] != filters["hold_reason"]:
		return False
	if filters.get("outcome") and record["outcome"] != filters["outcome"]:
		return False
	if filters.get("reviewer") and record["reviewer"] != filters["reviewer"]:
		return False
	decided = record.get("decided_at")
	if filters.get("from_date") and (not decided or str(decided) < str(filters["from_date"])):
		return False
	if filters.get("to_date") and (not decided or str(decided) > str(filters["to_date"]) + " 23:59:59"):
		return False
	return True


@frappe.whitelist()
def decision_history(filters=None, limit=100) -> dict:
	"""Paired settlement-decision history, newest first. Compliance / System Manager only."""
	if not can_send_decisions():
		return {"permitted": False, "count": 0, "records": []}

	if isinstance(filters, str):
		filters = _loads(filters)
	filters = filters if isinstance(filters, dict) else {}
	try:
		limit = max(1, min(int(limit), 1000))
	except ValueError, TypeError:
		limit = 100

	# Fetch a generous window of decision rows so sent/response pairs are not split by the cap.
	rows = frappe.get_all(
		_AUDIT,
		filters={"event_type": ["in", [_SENT, _RESPONSE]]},
		fields=[
			"event_type",
			"event_time",
			"outcome",
			"correlation_id",
			"harness_request_id",
			"error_code",
			"detail_json",
		],
		order_by="event_time desc",
		limit_page_length=max(limit * 4, 500),
	)

	# Pair by harness_request_id (unique per decision attempt — a session_ref may have several).
	paired: dict[str, dict] = {}
	for r in rows:
		rid = r.harness_request_id or f"_noid:{r.correlation_id}:{r.event_time}"
		rec = paired.setdefault(
			rid,
			{
				"request_id": r.harness_request_id,
				"session_ref": r.correlation_id,
				"decision": None,
				"reviewer": None,
				"decided_at": None,
				"hold_reason": None,
				"resulting_state": None,
				"idempotent": None,
				"outcome": None,
				"error_code": None,
				"response_time": None,
				"_has_sent": False,
				"_has_response": False,
			},
		)
		detail = _loads(r.detail_json)
		if r.event_type == _SENT:
			rec["_has_sent"] = True
			rec["decision"] = detail.get("decision")
			rec["reviewer"] = detail.get("reviewer")
			rec["decided_at"] = str(r.event_time) if r.event_time else None
			rec["hold_reason"] = detail.get("hold_reason")
		elif r.event_type == _RESPONSE:
			rec["_has_response"] = True
			rec["resulting_state"] = detail.get("resulting_state")
			rec["idempotent"] = detail.get("idempotent")
			rec["outcome"] = r.outcome
			rec["error_code"] = r.error_code
			rec["response_time"] = str(r.event_time) if r.event_time else None

	records = []
	for rec in paired.values():
		if rec["_has_sent"] and rec["_has_response"]:
			status = "responded"
		elif rec["_has_sent"]:
			status = "pending"  # sent, no response yet — show it, never hide
		else:
			status = "orphan_response"  # response with no sent — surface the anomaly
		rec["status"] = status
		rec["hold_reason_label"] = decision_render.hold_reason_label(rec["hold_reason"])
		rec["resulting_label"] = (
			decision_render.resulting_state_label(rec["resulting_state"]) if rec["resulting_state"] else ""
		)
		rec.pop("_has_sent", None)
		rec.pop("_has_response", None)
		if _matches(rec, filters):
			records.append(rec)

	# Newest first by the decision time (fall back to response time for orphan responses).
	records.sort(key=lambda x: x.get("decided_at") or x.get("response_time") or "", reverse=True)
	records = records[:limit]
	return {"permitted": True, "count": len(records), "records": records}

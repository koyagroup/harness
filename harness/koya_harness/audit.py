"""Best-effort audit writer for the Koya Harness Audit Log (Phase 3, G3).

Every mirror receive — and, later, every webhook decision (Phase 4) and ledger post
(Phase 8) — writes one append-only row. Writes are BEST-EFFORT: wrapped in try/except so
an audit failure can NEVER fail the receive. If the DB is sick, the mirror receive matters
more than the audit row. `detail` must carry key names + counts + outcomes ONLY — never
PII, never transaction values.
"""

import json

import frappe

from harness.koya_harness.log import get_logger

_AUDIT = "Koya Harness Audit Log"


def write_audit(
	event_type: str,
	correlation_id: str | None = None,
	harness_request_id: str | None = None,
	outcome: str = "success",
	detail: dict | None = None,
	error_code: str | None = None,
) -> None:
	"""Append one audit row. Never raises — any failure is logged and swallowed.

	`correlation_id` is Koya's body request_id (for cross-system pairing); for webhooks it
	is the relevant ref/session id. `harness_request_id` is the harness-side correlation id
	minted on receipt.
	"""
	try:
		doc = frappe.new_doc(_AUDIT)
		doc.event_type = event_type
		doc.event_time = frappe.utils.now_datetime()
		doc.correlation_id = correlation_id
		doc.harness_request_id = harness_request_id
		doc.outcome = outcome
		doc.error_code = error_code
		doc.detail_json = json.dumps(detail or {}, separators=(",", ":"))
		doc.insert(ignore_permissions=True)
	except Exception:
		get_logger().warning(f"audit write failed event={event_type}")

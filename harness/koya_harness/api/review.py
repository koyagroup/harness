"""Phase-3 read-only API for the review queue (compliance console).

Both endpoints are session-gated (`@frappe.whitelist()`, NOT allow_guest) AND
permission-gated server-side on `Koya Review Item` read — an ops user (no read perm) gets
an empty, not-permitted payload regardless of what the client JS chooses to draw. This is
defence in depth behind the page-level role gate (G5).

All display formatting is delegated to the pure `risk_render` helpers so the per-signal
value dispatch / sort / band logic stays unit-testable and single-sourced (no JS↔Python
drift). Read-only: nothing here writes, and there is NO approve/reject path (Phase 4).
"""

import json

import frappe

from harness.koya_harness import decision_render, risk_render
from harness.koya_harness.api.settlement import can_send_decisions

_REVIEW = "Koya Review Item"
_STALE_SECONDS = 180  # reuse the transactions-mirror cadence threshold (§5)


def _loads(raw):
	if not raw:
		return []
	try:
		data = json.loads(raw)
	except ValueError, TypeError:
		return []
	return data if isinstance(data, list) else []


def _age(now, received_at):
	if not received_at:
		return None
	return int((now - frappe.utils.get_datetime(received_at)).total_seconds())


def _truncate(text, n=80):
	text = text or ""
	return text if len(text) <= n else text[: n - 1] + "…"


@frappe.whitelist()
def review_queue_state() -> dict:
	"""List of current MANUAL_REVIEW items + header (count, last-received, stale). Rebuilt
	per transactions snapshot, so this is simply 'everything currently in the queue'."""
	if not frappe.has_permission(_REVIEW, "read"):
		return {"permitted": False, "count": 0, "items": []}

	now = frappe.utils.now_datetime()
	rows = frappe.get_all(
		_REVIEW,
		fields=[
			"name",
			"ref",
			"asset",
			"kes_amount",
			"risk_score",
			"risk_band",
			"risk_breakdown_json",
			"received_at",
		],
		order_by="received_at desc",
	)

	last_received = None
	items = []
	for r in rows:
		if r.received_at and (last_received is None or r.received_at > last_received):
			last_received = r.received_at
		top = risk_render.top_signal(_loads(r.risk_breakdown_json)) or {}
		items.append(
			{
				"ref": r.ref,
				"asset": r.asset,
				"kes_display": risk_render.format_kes(r.kes_amount),
				"score": r.risk_score,
				"band": r.risk_band,
				"band_class": risk_render.band_class(r.risk_band),
				"top_reason": _truncate(top.get("reason") or ""),
				"age_seconds": _age(now, r.received_at),
			}
		)

	age = _age(now, last_received)
	return {
		"permitted": True,
		"count": len(items),
		"last_received_at": str(last_received) if last_received else None,
		"age_seconds": age,
		"stale": age is not None and age > _STALE_SECONDS,
		"never_received": last_received is None,
		"items": items,
	}


@frappe.whitelist()
def review_item_detail(name: str) -> dict:
	"""Full detail for one review item: scalars + a server-rendered breakdown table.
	Read-only; no actions."""
	if not frappe.has_permission(_REVIEW, "read"):
		return {"permitted": False}
	if not frappe.db.exists(_REVIEW, name):
		return {"permitted": True, "found": False}

	doc = frappe.get_doc(_REVIEW, name)
	breakdown = _loads(doc.risk_breakdown_json)
	hold_reason = doc.get("hold_reason")
	return {
		"permitted": True,
		"found": True,
		"ref": doc.ref,
		"state": doc.state,
		# Phase 4: the hold-reason banner + the (server-rendered, single-sourced) reviewer
		# affordance. `can_decide` is a UI hint only — the real money-path gate is server-side
		# on the send method (settlement._require_decision_role).
		"hold_reason": hold_reason,
		"hold_reason_label": decision_render.hold_reason_label(hold_reason),
		"hold_reason_class": decision_render.hold_reason_class(hold_reason),
		"can_decide": can_send_decisions(),
		"confirm_approve": decision_render.confirmation_text(hold_reason, "APPROVE"),
		"confirm_reject": decision_render.confirmation_text(hold_reason, "REJECT"),
		"asset": doc.asset,
		"kes_amount": doc.kes_amount,
		"kes_display": risk_render.format_kes(doc.kes_amount),
		"asset_amount": doc.asset_amount,
		"created_at": str(doc.created_at) if doc.created_at else None,
		"updated_at": str(doc.updated_at) if doc.updated_at else None,
		"score": doc.risk_score,
		"band": doc.risk_band,
		"band_class": risk_render.band_class(doc.risk_band),
		"scorer_version": doc.scorer_version,
		"scorer_caption": f"Scored by engine v{doc.scorer_version}" if doc.scorer_version else "",
		"computed_at": str(doc.risk_computed_at) if doc.risk_computed_at else None,
		"computed_at_relative": frappe.utils.pretty_date(doc.risk_computed_at)
		if doc.risk_computed_at
		else "—",
		"received_at": str(doc.received_at) if doc.received_at else None,
		"breakdown_html": risk_render.render_breakdown_html(breakdown),
	}

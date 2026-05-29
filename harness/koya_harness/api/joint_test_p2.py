"""Phase-2 joint-test driver (harness side).

Companion to the Phase-1 four-outcome runner (`harness.api.joint_test`). Phase 2 has no
bad-request matrix to drive from our side — Koya pushes, we 2xx or we don't, and the next
snapshot corrects it. So the harness-side joint-test surface is a *receipt query*: it
reports the current state of both mirror snapshots so the Koya CTO can confirm push-lands,
stale-clears, and post-kill-switch resume by querying us.

Run any time during joint testing:
    bench --site <site> execute harness.koya_harness.api.joint_test_p2.run_mirror_smoke
"""

import frappe

_RATE_MIRROR = "Koya Rate Mirror"
_TXN_MIRROR = "Koya Transaction Mirror"
_RATE_STALE_S = 90
_TXN_STALE_S = 180


def _age_seconds(received_at):
	if not received_at:
		return None
	now = frappe.utils.now_datetime()
	return int((now - frappe.utils.get_datetime(received_at)).total_seconds())


@frappe.whitelist()
def run_mirror_smoke() -> dict:
	"""Return the current receipt state of both mirrors for joint-test paste-back."""
	rate = frappe.get_single(_RATE_MIRROR)
	txn = frappe.get_single(_TXN_MIRROR)

	rate_age = _age_seconds(rate.received_at)
	txn_age = _age_seconds(txn.received_at)

	return {
		"server_now": str(frappe.utils.now_datetime()),
		"rates": {
			"request_id": rate.request_id,
			"schema_version": rate.schema_version,
			"snapshot_at": str(rate.snapshot_at) if rate.snapshot_at else None,
			"received_at": str(rate.received_at) if rate.received_at else None,
			"age_seconds": rate_age,
			"stale": rate_age is not None and rate_age > _RATE_STALE_S,
			"never_received": rate.received_at is None,
		},
		"transactions": {
			"request_id": txn.request_id,
			"schema_version": txn.schema_version,
			"snapshot_at": str(txn.snapshot_at) if txn.snapshot_at else None,
			"received_at": str(txn.received_at) if txn.received_at else None,
			"age_seconds": txn_age,
			"stale": txn_age is not None and txn_age > _TXN_STALE_S,
			"never_received": txn.received_at is None,
			"pii_warning": txn.pii_warning,
		},
	}

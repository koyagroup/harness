"""G3 — Koya Harness Audit Log: write-only, append-only, best-effort.

Every mirror receive writes one audit row; a risk-validation warning writes a second.
Audit writes are best-effort — a failure must never fail the receive. The log is
append-only: no role has write/create/delete perms, and `on_trash` hard-blocks deletion.
`detail_json` carries key names + counts only — never PII / transaction values.
"""

import json
import time
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness import verify as V
from harness.koya_harness.api import mirrors
from harness.koya_harness.audit import write_audit
from harness.koya_harness.sign import compute_signature

TEST_SECRET = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
_AUDIT = "Koya Harness Audit Log"


class FakeReq:
	def __init__(self, headers, body):
		self.headers = headers
		self._body = body

	def get_data(self):
		return self._body


def _signed_headers(raw):
	ts = str(int(time.time()))
	nonce = str(uuid.uuid4()).lower()
	return {
		"Content-Type": "application/json",
		"X-Harness-Timestamp": ts,
		"X-Harness-Nonce": nonce,
		"X-Harness-Signature": compute_signature(TEST_SECRET, ts, nonce, raw),
	}


def _rates_body():
	return {
		"request_id": str(uuid.uuid4()),
		"schema_version": 1,
		"snapshot_at": "2026-06-01T10:14:56.789Z",
		"rates": [
			{
				"asset": "BTC",
				"pair": "BTC/KES",
				"mid_rate": "5234567.89",
				"source": "binance",
				"fetched_at": "2026-06-01T10:14:55.000Z",
				"stale": False,
			}
		],
	}


def _risk(score=78):
	return {
		"score": score,
		"band": "REVIEW",
		"scorer_version": 1,
		"computed_at": "2026-06-01T10:14:33.000Z",
		"breakdown": [
			{
				"signal": "amount_vs_kyc_tier",
				"value": "95000",
				"weight": 25,
				"contribution": 23,
				"reason": "r",
			}
		],
	}


def _txn_body(risk=None):
	item = {
		"ref": "KYA-2026-06-01-7001",
		"state": "MANUAL_REVIEW",
		"asset": "BTC",
		"created_at": "2026-06-01T10:00:00.000Z",
		"updated_at": "2026-06-01T10:14:00.000Z",
		"kes_amount": "95000.00",
		"asset_amount": "0.018",
	}
	if risk is not None:
		item["risk"] = risk
	return {
		"request_id": str(uuid.uuid4()),
		"schema_version": 2,
		"snapshot_at": "2026-06-01T10:14:56.789Z",
		"status_counts": {"MANUAL_REVIEW": 1, "COMPLETED": 1},
		"recent": [item],
		"recent_count": 1,
	}


class TestAuditLog(IntegrationTestCase):
	def setUp(self):
		frappe.local.response = frappe._dict()
		p1 = patch.object(V, "get_outbound_secret", return_value=TEST_SECRET)
		p2 = patch.object(frappe.db, "commit")
		p1.start()
		p2.start()
		self.addCleanup(p1.stop)
		self.addCleanup(p2.stop)

	def _call(self, fn, body):
		raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
		frappe.local.request = FakeReq(_signed_headers(raw), raw)
		frappe.local.response = frappe._dict()
		return fn()

	def _rows(self, correlation_id):
		return frappe.get_all(
			_AUDIT,
			filters={"correlation_id": correlation_id},
			fields=["event_type", "outcome", "detail_json", "error_code", "harness_request_id"],
		)

	# ---- one row per receive ----------------------------------------------
	def test_rates_push_writes_one_row(self):
		body = _rates_body()
		res = self._call(mirrors.rates, body)
		self.assertTrue(res["ok"])
		rows = self._rows(body["request_id"])
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].event_type, "mirror_rates_received")
		self.assertEqual(rows[0].outcome, "success")

	def test_transactions_push_writes_one_row(self):
		body = _txn_body(risk=_risk())
		res = self._call(mirrors.transactions, body)
		self.assertTrue(res["ok"])
		rows = self._rows(body["request_id"])
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].event_type, "mirror_transactions_received")

	# ---- risk warning → an extra row --------------------------------------
	def test_risk_warning_writes_two_rows(self):
		body = _txn_body(risk=_risk(score=150))  # out-of-range score → G1 warning
		res = self._call(mirrors.transactions, body)
		self.assertTrue(res["ok"])
		rows = self._rows(body["request_id"])
		types = sorted(r.event_type for r in rows)
		self.assertEqual(types, ["mirror_risk_validation_warning", "mirror_transactions_received"])
		warning = next(r for r in rows if r.event_type == "mirror_risk_validation_warning")
		self.assertEqual(warning.outcome, "warning")
		self.assertIn("risk_score_range", warning.detail_json)

	# ---- detail carries no PII / values -----------------------------------
	def test_detail_json_has_no_pii_values(self):
		body = _txn_body(risk=_risk())
		self._call(mirrors.transactions, body)
		rows = self._rows(body["request_id"])
		detail = rows[0].detail_json
		self.assertIn("recent_count", detail)  # keys + counts present
		self.assertNotIn("95000", detail)  # the KES amount never appears
		self.assertNotIn("KYA-2026-06-01-7001", detail)  # the ref never appears

	# ---- best-effort: an audit failure never breaks the receive -----------
	def test_audit_failure_does_not_break_receive(self):
		body = _rates_body()
		with patch.object(frappe, "new_doc", side_effect=Exception("audit DB down")):
			res = self._call(mirrors.rates, body)
		self.assertTrue(res["ok"])  # receive survives
		self.assertEqual(len(self._rows(body["request_id"])), 0)  # no row written

	# ---- append-only -------------------------------------------------------
	def test_delete_is_blocked(self):
		write_audit("test_event", correlation_id="cid-del")
		name = frappe.db.get_value(_AUDIT, {"correlation_id": "cid-del"}, "name")
		self.assertIsNotNone(name)
		with self.assertRaises(frappe.exceptions.ValidationError):
			frappe.delete_doc(_AUDIT, name, ignore_permissions=True)  # bypass perms → hits on_trash

	def test_no_write_create_delete_perms(self):
		meta = frappe.get_meta(_AUDIT)
		self.assertTrue(meta.permissions)  # has read perms
		for p in meta.permissions:
			self.assertEqual(p.write, 0)
			self.assertEqual(p.create, 0)
			self.assertEqual(p.delete, 0)

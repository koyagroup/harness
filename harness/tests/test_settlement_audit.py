"""G5 — every decision SEND and RESPONSE is audited (append-only, value-free).

Two rows per decision: `settlement_decision_sent` (decision metadata only — decision,
reviewer, reason presence/length, hold_reason; NEVER the reason text, an amount, or PII) and
`settlement_decision_response` (resulting_state + idempotent + outcome + error_code). The
audit is best-effort: a write failure must NEVER break the money decision, but for a money
action it is logged prominently.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness.api import settlement

_AUDIT = "Koya Harness Audit Log"
# Anything that would betray an amount, a destination, or the reviewer's free text.
_FORBIDDEN_SUBSTRINGS = ("95000", "amount", "destination", "address", "btc1", "0.0")


class TestSettlementAudit(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(lambda: frappe.set_user("Administrator"))
		frappe.set_user("Administrator")  # System Manager -> passes the gate

	def _rows(self, request_id, event_type):
		return frappe.get_all(
			_AUDIT,
			filters={"harness_request_id": request_id, "event_type": event_type},
			fields=["event_type", "outcome", "error_code", "detail_json", "correlation_id"],
		)

	def test_send_and_response_rows_written(self):
		res = settlement.send_settlement_decision("KYA-AUDIT-1", "APPROVE")
		rid = res["request_id"]
		sent = self._rows(rid, "settlement_decision_sent")
		resp = self._rows(rid, "settlement_decision_response")
		self.assertEqual(len(sent), 1)
		self.assertEqual(len(resp), 1)
		self.assertEqual(sent[0].correlation_id, "KYA-AUDIT-1")
		self.assertEqual(resp[0].outcome, "success")
		d = json.loads(resp[0].detail_json)
		self.assertEqual(d["resulting_state"], "PAYMENT_PENDING")  # simulated accepted
		self.assertFalse(d["idempotent"])

	def test_sent_detail_is_value_free(self):
		# A reason with an embedded amount-like token must NOT leak into the audit row.
		res = settlement.send_settlement_decision(
			"KYA-AUDIT-2", "REJECT", reason="structuring near 95000 to btc1qxyz"
		)
		rid = res["request_id"]
		sent = self._rows(rid, "settlement_decision_sent")
		blob = sent[0].detail_json
		d = json.loads(blob)
		# decision metadata present...
		self.assertEqual(d["decision"], "REJECT")
		self.assertTrue(d["reason_present"])
		self.assertIn("reason_len", d)
		# ...but the reason TEXT and any amount/destination token absent.
		self.assertNotIn("structuring", blob)
		self.assertNotIn("btc1qxyz", blob)
		for token in _FORBIDDEN_SUBSTRINGS:
			self.assertNotIn(token, blob, f"value-bearing token {token!r} leaked into audit")

	def test_response_row_carries_error_code_on_failure(self):
		# Force a 404 through the live-fire path to exercise the failure audit.
		def fake_post(path, payload, with_status=False):
			return ({"ok": False, "error": {"code": "not_found"}}, 404)

		with patch.object(settlement, "_live_fire_enabled", return_value=True):
			with patch.object(settlement, "post_signed", side_effect=fake_post):
				res = settlement.send_settlement_decision("KYA-AUDIT-3", "APPROVE")
		rid = res["request_id"]
		resp = self._rows(rid, "settlement_decision_response")
		self.assertEqual(resp[0].outcome, "failure")
		self.assertEqual(resp[0].error_code, "not_found")

	def test_audit_failure_does_not_break_decision(self):
		# write_audit raising must not break the money flow (the wrapper swallows + warns).
		with patch.object(settlement, "write_audit", side_effect=RuntimeError("db down")):
			res = settlement.send_settlement_decision("KYA-AUDIT-4", "APPROVE")
		self.assertTrue(res["ok"])  # decision flow survived the audit failure
		self.assertEqual(res["resulting_state"], "PAYMENT_PENDING")

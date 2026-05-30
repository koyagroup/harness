"""G2 — the inbound-signed settlement-decision request.

The body is contract-exact and MONEY-FREE: request_id (uuid4 lowercase), session_ref,
decision, reviewer (audit only), decided_at (RFC3339 ms UTC), reason (REJECT only). There is
NO amount / destination / asset — that absence is the injection-defense property. Signing
reuses `client.post_signed` (inbound secret), never a hand-rolled signer, and the real POST
only happens when the live-fire flag is ON (default OFF -> a simulated response).
"""

import re
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness.api import settlement

_UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_RFC3339_MS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_FORBIDDEN = ("amount", "kes_amount", "asset", "asset_amount", "destination", "address", "payout")


class TestSettlementSend(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(lambda: frappe.set_user("Administrator"))
		# Administrator holds System Manager -> passes the G1 gate.
		frappe.set_user("Administrator")

	# ---- body shape (capture via the live-fire path so we see the exact signed body) ----
	def _capture_body(self, decision, reason=None):
		captured = {}

		def fake_post(path, payload, with_status=False):
			captured["path"] = path
			captured["payload"] = payload
			body = {"ok": True, "data": {"resulting_state": "PAYMENT_PENDING", "idempotent": False}}
			return (body, 200) if with_status else body

		with patch.object(settlement, "_live_fire_enabled", return_value=True):
			with patch.object(settlement, "post_signed", side_effect=fake_post):
				settlement.send_settlement_decision("KYA-SEND-1", decision, reason=reason)
		return captured

	def test_body_shape_is_contract_exact(self):
		cap = self._capture_body("APPROVE")
		self.assertEqual(cap["path"], "/internal/harness/settlement-decision")
		body = cap["payload"]
		self.assertTrue(_UUID4.match(body["request_id"]), body["request_id"])
		self.assertEqual(body["request_id"], body["request_id"].lower())
		self.assertTrue(_RFC3339_MS.match(body["decided_at"]), body["decided_at"])
		self.assertEqual(body["decision"], "APPROVE")
		self.assertEqual(body["session_ref"], "KYA-SEND-1")
		self.assertEqual(body["reviewer"], frappe.session.user)

	def test_body_carries_no_money_fields(self):
		body = self._capture_body("REJECT", reason="suspected structuring")["payload"]
		for k in _FORBIDDEN:
			self.assertNotIn(k, body, f"money field {k!r} must never be in the decision body")

	def test_approve_omits_reason(self):
		body = self._capture_body("APPROVE")["payload"]
		self.assertNotIn("reason", body)

	def test_reject_includes_reason(self):
		body = self._capture_body("REJECT", reason="kyc mismatch")["payload"]
		self.assertEqual(body["reason"], "kyc mismatch")

	# ---- reject-reason validation: never send an invalid decision ----
	@patch.object(settlement, "post_signed")
	def test_reject_without_reason_is_structural_error_no_send(self, mock_post):
		res = settlement.send_settlement_decision("KYA-SEND-1", "REJECT")
		self.assertFalse(res["ok"])
		self.assertEqual(res["error_code"], "validation_error")
		self.assertFalse(res["sent"])
		mock_post.assert_not_called()

	@patch.object(settlement, "post_signed")
	def test_invalid_decision_is_structural_error_no_send(self, mock_post):
		res = settlement.send_settlement_decision("KYA-SEND-1", "MAYBE")
		self.assertFalse(res["ok"])
		self.assertEqual(res["error_code"], "validation_error")
		mock_post.assert_not_called()

	# ---- live-fire seam ----
	@patch.object(settlement, "post_signed")
	def test_live_fire_off_does_not_post(self, mock_post):
		res = settlement.send_settlement_decision("KYA-SEND-1", "APPROVE")
		mock_post.assert_not_called()  # default OFF -> simulated, nothing leaves the box
		self.assertTrue(res["ok"])
		self.assertFalse(res["live_fire"])

	def test_live_fire_on_calls_post_signed_with_status(self):
		seen = {}

		def fake_post(path, payload, with_status=False):
			seen["with_status"] = with_status
			seen["path"] = path
			return ({"ok": True, "data": {"resulting_state": "REJECTED", "idempotent": False}}, 200)

		with patch.object(settlement, "_live_fire_enabled", return_value=True):
			with patch.object(settlement, "post_signed", side_effect=fake_post) as mp:
				res = settlement.send_settlement_decision("KYA-SEND-1", "REJECT", reason="r")
		mp.assert_called_once()
		self.assertEqual(seen["path"], "/internal/harness/settlement-decision")
		self.assertTrue(seen["with_status"])  # opts into the (body, status) tuple
		self.assertTrue(res["live_fire"])

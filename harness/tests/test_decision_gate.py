"""G1 — the server-side compliance ACTION gate (the money-path control).

Independent of the Phase-3 READ gate (review.py): that gates VIEWING the queue; this gates
SENDING a settlement decision. The gate is on the send method itself, so it holds no matter
what the page JS draws. Only `koya_harness_compliance` OR `System Manager` may send; everyone
else (including `koya_harness_ops`, who can read mirrors) is blocked before any body is built
or any transport is attempted.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness.api import settlement

_COMPLIANCE = "koya_harness_compliance"
_OPS = "koya_harness_ops"


class TestDecisionGate(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(lambda: frappe.set_user("Administrator"))

	def _make_user(self, email, roles):
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		user = frappe.new_doc("User")
		user.email = email
		user.first_name = "Test"
		user.send_welcome_email = 0
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)
		if roles:
			user.add_roles(*roles)
		return email

	@patch.object(settlement, "post_signed")
	def test_user_without_decision_role_blocked(self, mock_post):
		frappe.set_user(self._make_user("p4_nobody@harness.test", []))
		with self.assertRaises(frappe.PermissionError):
			settlement.send_settlement_decision("KYA-GATE-1", "APPROVE")
		mock_post.assert_not_called()  # no body built, no POST attempted

	@patch.object(settlement, "post_signed")
	def test_ops_user_blocked(self, mock_post):
		frappe.set_user(self._make_user("p4_ops@harness.test", [_OPS]))
		with self.assertRaises(frappe.PermissionError):
			settlement.send_settlement_decision("KYA-GATE-1", "REJECT", reason="x")
		mock_post.assert_not_called()

	@patch.object(settlement, "post_signed")
	def test_compliance_user_passes_gate(self, mock_post):
		frappe.set_user(self._make_user("p4_comp@harness.test", [_COMPLIANCE]))
		res = settlement.send_settlement_decision("KYA-GATE-1", "APPROVE")
		self.assertTrue(res["ok"])  # proceeded past the gate to the (simulated) send path
		mock_post.assert_not_called()  # live-fire OFF -> no real POST

	@patch.object(settlement, "post_signed")
	def test_system_manager_passes_gate(self, mock_post):
		frappe.set_user(self._make_user("p4_sm@harness.test", ["System Manager"]))
		res = settlement.send_settlement_decision("KYA-GATE-1", "APPROVE")
		self.assertTrue(res["ok"])
		mock_post.assert_not_called()

"""G6 — the live-fire gate chain (the money-path safety property).

Two INDEPENDENT things must both hold before a real decision leaves the box:
  1. `harness_phase4_live_fire` is True in site_config (default / absent = False).
  2. The caller passes the G1 compliance/System-Manager gate.
The flag does NOT bypass the gate, and the gate does NOT enable the POST on its own. With the
flag OFF (the shipped default) NO real POST happens under approve, reject, OR a retry path.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness.api import settlement

_COMPLIANCE = "koya_harness_compliance"


class TestLiveFireGate(IntegrationTestCase):
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

	# ---- flag OFF (default): NO real POST under any decision path ----
	@patch.object(settlement, "post_signed")
	def test_flag_off_no_post_on_approve_reject_retry(self, mock_post):
		frappe.set_user(self._make_user("p4_lf_comp@harness.test", [_COMPLIANCE]))
		# default: flag absent == False
		settlement.send_settlement_decision("KYA-LF-1", "APPROVE")
		settlement.send_settlement_decision("KYA-LF-2", "REJECT", reason="r")
		# a "retry" is just another send (fresh request_id) — still must not post
		settlement.send_settlement_decision("KYA-LF-1", "APPROVE")
		mock_post.assert_not_called()

	def test_default_live_fire_is_false(self):
		# Absence of the key must read as OFF.
		self.assertFalse(bool(frappe.conf.get("harness_phase4_live_fire", False)))

	# ---- flag ON does NOT bypass the compliance gate ----
	@patch.object(settlement, "post_signed")
	def test_flag_on_still_requires_compliance(self, mock_post):
		frappe.set_user(self._make_user("p4_lf_nobody@harness.test", []))
		with patch.object(settlement, "_live_fire_enabled", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				settlement.send_settlement_decision("KYA-LF-3", "APPROVE")
		mock_post.assert_not_called()  # gate blocked it before any POST

	# ---- flag ON + compliance -> the real signed POST path is taken (mocked) ----
	def test_flag_on_and_compliance_takes_post_path(self):
		frappe.set_user(self._make_user("p4_lf_comp2@harness.test", [_COMPLIANCE]))

		def fake_post(path, payload, with_status=False):
			return ({"ok": True, "data": {"resulting_state": "PAYMENT_PENDING", "idempotent": False}}, 200)

		with patch.object(settlement, "_live_fire_enabled", return_value=True):
			with patch.object(settlement, "post_signed", side_effect=fake_post) as mp:
				res = settlement.send_settlement_decision("KYA-LF-4", "APPROVE")
		mp.assert_called_once()
		self.assertTrue(res["ok"])
		self.assertTrue(res["live_fire"])

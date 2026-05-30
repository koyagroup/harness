"""G5 — landing page (Koya Operations Console) role-gated sections.

The page renders three sections; the Review Queue section must be visible to compliance
(and System Manager) but NOT to ops. The visual gate (JS reading `frappe.user_roles`) is
backed by a server-side permission gate: `review_queue_state` returns `permitted: False`
for a user without read on Koya Review Item. These tests exercise that data-layer gate as
real users — the testable surface of the per-section visibility difference.
"""

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness.api import review

_COMPLIANCE = "koya_harness_compliance"
_OPS = "koya_harness_ops"


class TestLandingRoleGating(IntegrationTestCase):
	def _make_user(self, email, roles):
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		user = frappe.new_doc("User")
		user.email = email
		user.first_name = "Test"
		user.send_welcome_email = 0
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)
		user.add_roles(*roles)
		return email

	def _as_user(self, email):
		frappe.set_user(email)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_ops_user_review_section_not_permitted(self):
		email = self._make_user("ops_landing@harness.test", [_OPS])
		self._as_user(email)
		state = review.review_queue_state()
		self.assertFalse(state["permitted"])
		self.assertEqual(state["items"], [])

	def test_compliance_user_review_section_permitted(self):
		email = self._make_user("compliance_landing@harness.test", [_COMPLIANCE])
		self._as_user(email)
		state = review.review_queue_state()
		self.assertTrue(state["permitted"])

	def test_landing_page_exists_and_role_gated(self):
		page = frappe.get_doc("Page", "koya-harness-home")
		page_roles = {r.role for r in page.roles}
		self.assertEqual(page_roles, {"System Manager", _COMPLIANCE, _OPS})

	def test_workspace_exists_and_role_gated(self):
		ws = frappe.get_doc("Workspace", "Koya Harness")
		ws_roles = {r.role for r in ws.roles}
		self.assertEqual(ws_roles, {"System Manager", _COMPLIANCE, _OPS})

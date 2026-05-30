"""G4 — staff role boundaries.

Two roles, auto-created on migrate from the doctype permission tables:
  koya_harness_compliance — reads Koya Review Item, Koya Harness Audit Log, both mirrors.
  koya_harness_ops        — reads both mirrors + Koya Harness Audit Log, NOT Review Item.

Verified two ways: real per-user `frappe.has_permission` checks (the boundary that matters
— ops must not see the review queue), and the doctype permission tables (the full matrix).
Operator assigns real staff users later; that is out of scope.
"""

import frappe
from frappe.tests import IntegrationTestCase

_REVIEW = "Koya Review Item"
_AUDIT = "Koya Harness Audit Log"
_RATE = "Koya Rate Mirror"
_TXN = "Koya Transaction Mirror"
_COMPLIANCE = "koya_harness_compliance"
_OPS = "koya_harness_ops"


class TestRoles(IntegrationTestCase):
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

	def _has_read_role(self, doctype, role):
		return any(p.role == role and p.read for p in frappe.get_meta(doctype).permissions)

	# ---- existence ---------------------------------------------------------
	def test_roles_exist(self):
		self.assertTrue(frappe.db.exists("Role", _COMPLIANCE))
		self.assertTrue(frappe.db.exists("Role", _OPS))

	# ---- the boundary that matters: ops must NOT see the review queue ------
	def test_ops_cannot_read_review_item(self):
		email = self._make_user("ops_only@harness.test", [_OPS])
		self.assertFalse(frappe.has_permission(_REVIEW, ptype="read", user=email))

	def test_compliance_can_read_review_item(self):
		email = self._make_user("compliance_only@harness.test", [_COMPLIANCE])
		self.assertTrue(frappe.has_permission(_REVIEW, ptype="read", user=email))

	def test_compliance_reads_audit_and_mirrors(self):
		email = self._make_user("compliance_only@harness.test", [_COMPLIANCE])
		self.assertTrue(frappe.has_permission(_AUDIT, ptype="read", user=email))
		self.assertTrue(frappe.has_permission(_RATE, ptype="read", user=email))
		self.assertTrue(frappe.has_permission(_TXN, ptype="read", user=email))

	def test_ops_reads_audit_and_mirrors(self):
		email = self._make_user("ops_only@harness.test", [_OPS])
		self.assertTrue(frappe.has_permission(_AUDIT, ptype="read", user=email))
		self.assertTrue(frappe.has_permission(_RATE, ptype="read", user=email))
		self.assertTrue(frappe.has_permission(_TXN, ptype="read", user=email))

	# ---- the full matrix at the permission-table level ---------------------
	def test_permission_matrix(self):
		# compliance reads everything in scope.
		self.assertTrue(self._has_read_role(_REVIEW, _COMPLIANCE))
		self.assertTrue(self._has_read_role(_AUDIT, _COMPLIANCE))
		self.assertTrue(self._has_read_role(_RATE, _COMPLIANCE))
		self.assertTrue(self._has_read_role(_TXN, _COMPLIANCE))
		# ops reads mirrors + audit, NOT the review queue.
		self.assertFalse(self._has_read_role(_REVIEW, _OPS))
		self.assertTrue(self._has_read_role(_AUDIT, _OPS))
		self.assertTrue(self._has_read_role(_RATE, _OPS))
		self.assertTrue(self._has_read_role(_TXN, _OPS))

	def test_no_role_writes_review_or_audit(self):
		for dt in (_REVIEW, _AUDIT):
			for p in frappe.get_meta(dt).permissions:
				self.assertEqual(p.write, 0, f"{dt}/{p.role} should have no write")
				self.assertEqual(p.delete, 0, f"{dt}/{p.role} should have no delete")

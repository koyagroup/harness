"""G4 — the reviewer approve/reject affordance (the parts that are Python-testable).

This bench has no JS unit runner (Phase-3 page JS was verified by rendered dump + manual
login walk-through), so the page's button rendering / confirm-dialog wiring is verified
manually. What IS unit-tested here is the single-sourced display logic the page renders
verbatim — the (hold_reason x decision) confirmation matrix and the hold-reason banner copy —
plus the detail endpoint that feeds them and the `can_decide` UI hint per role. The heaviest
case: a REJECT on a post-payment (btc_delivery_retry_exhausted) hold must read as a REFUND
OBLIGATION, distinct from a clean pre-payment decline.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness import decision_render
from harness.koya_harness.api import mirrors, review, settlement

_REVIEW = "Koya Review Item"
_COMPLIANCE = "koya_harness_compliance"
_OPS = "koya_harness_ops"
_POSTPAY = "btc_delivery_retry_exhausted"


class TestConfirmationMatrix(IntegrationTestCase):
	"""The four (hold_reason x decision) cases — the money-safety copy."""

	def test_approve_prepay(self):
		t = decision_render.confirmation_text("risk_review_required", "APPROVE")
		self.assertIn("resume", t.lower())
		self.assertNotIn("retry", t.lower())

	def test_approve_postpay_mentions_retry_and_money_in(self):
		t = decision_render.confirmation_text(_POSTPAY, "APPROVE")
		self.assertIn("retry", t.lower())
		self.assertIn("collected", t.lower())

	def test_reject_prepay_clean_decline(self):
		t = decision_render.confirmation_text("compliance_review_required", "REJECT")
		self.assertIn("no funds were collected", t.lower())
		self.assertNotIn("refund", t.lower())

	def test_reject_postpay_is_refund_obligation(self):
		t = decision_render.confirmation_text(_POSTPAY, "REJECT")
		self.assertIn("refund", t.lower())
		self.assertIn("owed", t.lower())

	def test_postpay_reject_reads_differently_from_prepay_reject(self):
		prepay = decision_render.confirmation_text("risk_review_required", "REJECT")
		postpay = decision_render.confirmation_text(_POSTPAY, "REJECT")
		self.assertNotEqual(prepay, postpay)


class TestHoldReasonBanner(IntegrationTestCase):
	def test_three_known_reasons(self):
		self.assertIn("risk review", decision_render.hold_reason_label("risk_review_required").lower())
		self.assertIn("compliance", decision_render.hold_reason_label("compliance_review_required").lower())
		self.assertIn("payment received", decision_render.hold_reason_label(_POSTPAY).lower())

	def test_classes(self):
		self.assertEqual(decision_render.hold_reason_class("risk_review_required"), "prepay")
		self.assertEqual(decision_render.hold_reason_class(_POSTPAY), "postpay")  # money-in, distinct
		self.assertEqual(decision_render.hold_reason_class(None), "none")
		self.assertEqual(decision_render.hold_reason_class("brand_new_reason"), "other")

	def test_unknown_reason_renders_generically_no_crash(self):
		self.assertIn("brand_new_reason", decision_render.hold_reason_label("brand_new_reason"))

	def test_empty_reason_no_banner(self):
		self.assertEqual(decision_render.hold_reason_label(None), "")
		self.assertEqual(decision_render.hold_reason_label(""), "")


class TestDetailEndpoint(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(lambda: frappe.set_user("Administrator"))
		frappe.set_user("Administrator")
		self.ref = "KYA-DECISION-UI-1"
		if frappe.db.exists(_REVIEW, self.ref):
			frappe.delete_doc(_REVIEW, self.ref, force=True, ignore_permissions=True)
		doc = frappe.new_doc(_REVIEW)
		doc.ref = self.ref
		doc.state = "MANUAL_REVIEW"
		doc.hold_reason = _POSTPAY
		doc.risk_score = 80
		doc.risk_band = "REVIEW"
		doc.risk_breakdown_json = "[]"
		doc.received_at = frappe.utils.now_datetime()
		doc.insert(ignore_permissions=True)

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

	def test_detail_returns_hold_reason_and_can_decide_for_compliance(self):
		frappe.set_user(self._make_user("p4_ui_comp@harness.test", [_COMPLIANCE]))
		d = review.review_item_detail(self.ref)
		self.assertTrue(d["permitted"])
		self.assertTrue(d["found"])
		self.assertEqual(d["hold_reason"], _POSTPAY)
		self.assertEqual(d["hold_reason_class"], "postpay")
		self.assertIn("PAYMENT RECEIVED", d["hold_reason_label"])
		self.assertTrue(d["can_decide"])
		self.assertIn("REFUND", d["confirm_reject"].upper())  # the heavy post-payment copy

	def test_ops_cannot_read_detail(self):
		frappe.set_user(self._make_user("p4_ui_ops@harness.test", [_OPS]))
		d = review.review_item_detail(self.ref)
		self.assertFalse(d["permitted"])  # ops has no read perm on the review item at all

	# ---- server-side reject-reason validation (the gate is server-side, not only the JS) ----
	@patch.object(settlement, "post_signed")
	def test_server_rejects_empty_reason(self, mock_post):
		frappe.set_user(self._make_user("p4_ui_comp2@harness.test", [_COMPLIANCE]))
		res = settlement.send_settlement_decision(self.ref, "REJECT", reason="   ")
		self.assertFalse(res["ok"])
		self.assertEqual(res["error_code"], "validation_error")
		mock_post.assert_not_called()


class TestReconcileCapturesHoldReason(IntegrationTestCase):
	"""A v2 mirror item carrying hold_reason -> the review item stores it (forward-compat:
	absent -> None, never blocks the upsert)."""

	def test_hold_reason_captured_from_mirror_item(self):
		ref = "KYA-HOLD-CAP-1"
		item = {
			"ref": ref,
			"state": "MANUAL_REVIEW",
			"hold_reason": "risk_review_required",
			"asset": "BTC",
			"kes_amount": "95000",
			"asset_amount": "0.01",
			"risk": {"score": 75, "band": "REVIEW", "scorer_version": 1, "breakdown": []},
		}
		mirrors._reconcile_review_items([item], frappe.utils.now_datetime())
		self.assertEqual(frappe.db.get_value(_REVIEW, ref, "hold_reason"), "risk_review_required")

	def test_hold_reason_absent_is_none_not_error(self):
		ref = "KYA-HOLD-CAP-2"
		item = {
			"ref": ref,
			"state": "MANUAL_REVIEW",
			"asset": "BTC",
			"kes_amount": "1000",
			"risk": {"score": 60, "band": "REVIEW", "scorer_version": 1, "breakdown": []},
		}
		mirrors._reconcile_review_items([item], frappe.utils.now_datetime())
		self.assertIsNone(frappe.db.get_value(_REVIEW, ref, "hold_reason"))

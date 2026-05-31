"""HARNESS-FILTER-FIX — all three MANUAL_REVIEW hold types surface + decide correctly.

The v3 mirror sends three hold types: risk_review_required (carries a `risk` object),
compliance_review_required and btc_delivery_retry_exhausted (carry `hold_reason`, NO risk
object). The reconcile filter now queues `MANUAL_REVIEW AND (risk OR hold_reason)`, so all
three reach the queue. A no-risk hold renders the banner + a no-risk note (NEVER a 0-score
or an empty breakdown table); the reason-aware confirmation fires per (type x decision) —
especially the post-payment delivery REJECT = REFUND-obligation wording.
"""

import json
import time
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness import verify as V
from harness.koya_harness.api import review
from harness.koya_harness.sign import compute_signature

TEST_SECRET = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
_REVIEW = "Koya Review Item"
_COMPLIANCE = "koya_harness_compliance"


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


def _risk():
	return {
		"score": 82,
		"band": "REVIEW",
		"scorer_version": 3,
		"computed_at": "2026-06-01T10:14:33.000Z",
		"breakdown": [
			{
				"signal": "amount_vs_kyc_tier",
				"value": "95000",
				"weight": 25,
				"contribution": 23,
				"reason": "KES 95,000 vs Tier-1 limit",
			}
		],
	}


def _item(ref, state="MANUAL_REVIEW", hold_reason=None, risk=None):
	item = {
		"ref": ref,
		"state": state,
		"asset": "BTC",
		"created_at": "2026-06-01T10:00:00.000Z",
		"updated_at": "2026-06-01T10:14:00.000Z",
		"kes_amount": "95000.00",
		"asset_amount": "0.018",
	}
	if hold_reason is not None:
		item["hold_reason"] = hold_reason
	if risk is not None:
		item["risk"] = risk
	return item


# The three hold types + a COMPLETED control.
RISK = _item("H-RISK", hold_reason="risk_review_required", risk=_risk())
COMPLIANCE = _item("H-COMP", hold_reason="compliance_review_required")  # no risk object
DELIVERY = _item("H-DELIV", hold_reason="btc_delivery_retry_exhausted")  # no risk, post-payment
DONE = _item("H-DONE", state="COMPLETED")


def _body(recent):
	return {
		"request_id": str(uuid.uuid4()),
		"schema_version": 3,
		"snapshot_at": "2026-06-01T10:14:56.789Z",
		"status_counts": {"MANUAL_REVIEW": 3, "COMPLETED": 1},
		"recent": recent,
		"recent_count": len(recent),
	}


class TestAllHoldTypes(IntegrationTestCase):
	def setUp(self):
		frappe.local.response = frappe._dict()
		p1 = patch.object(V, "get_outbound_secret", return_value=TEST_SECRET)
		p2 = patch.object(frappe.db, "commit")
		p1.start()
		p2.start()
		self.addCleanup(p1.stop)
		self.addCleanup(p2.stop)
		self.addCleanup(lambda: frappe.set_user("Administrator"))
		frappe.db.delete(_REVIEW)
		from harness.koya_harness.api import mirrors

		raw = json.dumps(_body([RISK, COMPLIANCE, DELIVERY, DONE]), separators=(",", ":")).encode()
		frappe.local.request = FakeReq(_signed_headers(raw), raw)
		self.res = mirrors.transactions()

	def _make_user(self, email, roles):
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		u = frappe.new_doc("User")
		u.email = email
		u.first_name = "Test"
		u.send_welcome_email = 0
		u.flags.no_welcome_mail = True
		u.insert(ignore_permissions=True)
		u.add_roles(*roles)
		return email

	# ---- exactly the three MANUAL_REVIEW holds surface; COMPLETED does not ----
	def test_three_holds_surface_completed_excluded(self):
		self.assertTrue(self.res["ok"])
		self.assertEqual(frappe.db.count(_REVIEW), 3)
		for ref in ("H-RISK", "H-COMP", "H-DELIV"):
			self.assertTrue(frappe.db.exists(_REVIEW, ref), ref)
		self.assertFalse(frappe.db.exists(_REVIEW, "H-DONE"))

	# ---- has_risk stored correctly; no misleading 0-score for no-risk holds ----
	def test_has_risk_flag_and_no_misleading_score(self):
		self.assertEqual(frappe.db.get_value(_REVIEW, "H-RISK", "has_risk"), 1)
		self.assertEqual(frappe.db.get_value(_REVIEW, "H-COMP", "has_risk"), 0)
		self.assertEqual(frappe.db.get_value(_REVIEW, "H-DELIV", "has_risk"), 0)
		# queue API: risk shows score, the two no-risk holds show None (NOT 0)
		by_ref = {it["ref"]: it for it in review.review_queue_state()["items"]}
		self.assertEqual(by_ref["H-RISK"]["score"], 82)
		self.assertIsNone(by_ref["H-COMP"]["score"])
		self.assertIsNone(by_ref["H-DELIV"]["score"])

	# ---- detail: breakdown only when risk present; banner + note otherwise ----
	def test_detail_risk_hold_has_breakdown(self):
		d = review.review_item_detail("H-RISK")
		self.assertTrue(d["has_risk"])
		self.assertEqual(d["score"], 82)
		self.assertIn("amount_vs_kyc_tier", d["breakdown_html"])
		self.assertEqual(d["no_risk_note"], "")
		self.assertEqual(d["hold_reason_label"], "Held: risk review (pre-payment)")

	def test_detail_compliance_hold_banner_no_breakdown(self):
		d = review.review_item_detail("H-COMP")
		self.assertFalse(d["has_risk"])
		self.assertIsNone(d["score"])
		self.assertEqual(d["breakdown_html"], "")  # no empty/misleading table
		self.assertTrue(d["no_risk_note"])
		self.assertIn("compliance", d["hold_reason_label"].lower())

	def test_detail_delivery_hold_distinct_banner(self):
		d = review.review_item_detail("H-DELIV")
		self.assertFalse(d["has_risk"])
		self.assertEqual(d["breakdown_html"], "")
		self.assertEqual(d["hold_reason_class"], "postpay")  # money-in, styled distinct
		self.assertIn("PAYMENT RECEIVED", d["hold_reason_label"])
		self.assertIn("not risk-scored", d["no_risk_note"].lower())

	# ---- reason-aware confirmation fires per (type x decision) ----
	def test_confirmations_per_type(self):
		risk = review.review_item_detail("H-RISK")
		comp = review.review_item_detail("H-COMP")
		deliv = review.review_item_detail("H-DELIV")
		# pre-payment rejects = clean decline; delivery reject = REFUND obligation
		self.assertIn("no funds were collected", risk["confirm_reject"].lower())
		self.assertIn("no funds were collected", comp["confirm_reject"].lower())
		self.assertIn("REFUND", deliv["confirm_reject"].upper())
		self.assertIn("owed", deliv["confirm_reject"].lower())
		# delivery approve = retry BTC (money already in)
		self.assertIn("retry", deliv["confirm_approve"].lower())
		self.assertIn("resume", risk["confirm_approve"].lower())

	# ---- can_decide true for all three for a compliance reviewer ----
	def test_can_decide_for_compliance_on_all_three(self):
		frappe.set_user(self._make_user("p_allholds_comp@harness.test", [_COMPLIANCE]))
		for ref in ("H-RISK", "H-COMP", "H-DELIV"):
			self.assertTrue(review.review_item_detail(ref)["can_decide"], ref)

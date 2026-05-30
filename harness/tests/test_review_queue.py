"""G2 — review-queue reconciliation + read API, driven through the mirror receiver.

Snapshot mode: the queue is rebuilt on every transactions push (upsert MANUAL_REVIEW
items that carry a `risk` object, delete the rest). These tests push faked signed
snapshots in-process and assert the resulting `Koya Review Item` rows + the read-API
shapes. `frappe.db.commit` is patched so each test stays inside the IntegrationTestCase
transaction.
"""

import json
import time
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness import verify as V
from harness.koya_harness.api import mirrors, review
from harness.koya_harness.sign import compute_signature

TEST_SECRET = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
_REVIEW = "Koya Review Item"


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


def _risk(score=78, band="REVIEW", signal="amount_vs_kyc_tier"):
	return {
		"score": score,
		"band": band,
		"scorer_version": 1,
		"computed_at": "2026-06-01T10:14:33.000Z",
		"breakdown": [
			{
				"signal": signal,
				"value": "95000",
				"weight": 25,
				"contribution": 23,
				"reason": "KES 95,000 vs Tier-1 limit KES 100,000 (95%)",
			},
			{
				"signal": "first_transaction",
				"value": False,
				"weight": 10,
				"contribution": 0,
				"reason": "Repeat customer",
			},
		],
	}


def _item(ref, state="MANUAL_REVIEW", risk=None):
	item = {
		"ref": ref,
		"state": state,
		"asset": "BTC",
		"created_at": "2026-06-01T10:00:00.000Z",
		"updated_at": "2026-06-01T10:14:00.000Z",
		"kes_amount": "95000.00",
		"asset_amount": "0.018",
	}
	if risk is not None:
		item["risk"] = risk
	return item


def _body(recent):
	return {
		"request_id": str(uuid.uuid4()),
		"schema_version": 2,
		"snapshot_at": "2026-06-01T10:14:56.789Z",
		"status_counts": {"MANUAL_REVIEW": 1, "COMPLETED": 1},
		"recent": recent,
		"recent_count": len(recent),
	}


class TestReviewQueue(IntegrationTestCase):
	def setUp(self):
		frappe.local.response = frappe._dict()
		p1 = patch.object(V, "get_outbound_secret", return_value=TEST_SECRET)
		p2 = patch.object(frappe.db, "commit")  # keep writes inside the test transaction
		p1.start()
		p2.start()
		self.addCleanup(p1.stop)
		self.addCleanup(p2.stop)
		frappe.db.delete(_REVIEW)  # isolate from any prior committed rows

	def _push(self, recent):
		raw = json.dumps(_body(recent), separators=(",", ":")).encode("utf-8")
		frappe.local.request = FakeReq(_signed_headers(raw), raw)
		frappe.local.response = frappe._dict()
		return mirrors.transactions()

	# ---- reconciliation ----------------------------------------------------
	def test_three_manual_review_two_completed_only_three_rows(self):
		recent = [
			_item("R1", "MANUAL_REVIEW", _risk()),
			_item("R2", "MANUAL_REVIEW", _risk()),
			_item("R3", "MANUAL_REVIEW", _risk()),
			_item("C1", "COMPLETED", _risk()),  # COMPLETED + risk → still NOT queued
			_item("C2", "COMPLETED"),
		]
		res = self._push(recent)
		self.assertTrue(res["ok"])
		self.assertEqual(frappe.db.count(_REVIEW), 3)
		self.assertTrue(frappe.db.exists(_REVIEW, "R1"))
		self.assertFalse(frappe.db.exists(_REVIEW, "C1"))

	def test_subsequent_push_one_deleted_one_added(self):
		self._push(
			[
				_item("R1", "MANUAL_REVIEW", _risk()),
				_item("R2", "MANUAL_REVIEW", _risk()),
				_item("R3", "MANUAL_REVIEW", _risk()),
			]
		)
		self.assertEqual(frappe.db.count(_REVIEW), 3)
		# R1 drops out; R2/R3 remain; R4 is new.
		self._push(
			[
				_item("R2", "MANUAL_REVIEW", _risk()),
				_item("R3", "MANUAL_REVIEW", _risk()),
				_item("R4", "MANUAL_REVIEW", _risk()),
			]
		)
		self.assertEqual(frappe.db.count(_REVIEW), 3)
		self.assertFalse(frappe.db.exists(_REVIEW, "R1"))
		self.assertTrue(frappe.db.exists(_REVIEW, "R4"))

	def test_zero_manual_review_clears_queue(self):
		self._push([_item("R1", "MANUAL_REVIEW", _risk())])
		self.assertEqual(frappe.db.count(_REVIEW), 1)
		self._push([_item("C1", "COMPLETED")])  # no MANUAL_REVIEW items at all
		self.assertEqual(frappe.db.count(_REVIEW), 0)

	def test_manual_review_without_risk_not_queued(self):
		res = self._push([_item("R1", "MANUAL_REVIEW")])  # no risk object
		self.assertTrue(res["ok"])
		self.assertEqual(frappe.db.count(_REVIEW), 0)

	def test_upsert_updates_existing_row(self):
		self._push([_item("R1", "MANUAL_REVIEW", _risk(score=72))])
		self.assertEqual(frappe.db.get_value(_REVIEW, "R1", "risk_score"), 72)
		self._push([_item("R1", "MANUAL_REVIEW", _risk(score=88))])
		self.assertEqual(frappe.db.count(_REVIEW), 1)  # updated, not duplicated
		self.assertEqual(frappe.db.get_value(_REVIEW, "R1", "risk_score"), 88)

	# ---- degraded but non-crashing ----------------------------------------
	def test_malformed_int_score_still_queued(self):
		# score 101 is out of range (a G1 warning) but still an int → stored verbatim.
		self._push([_item("R1", "MANUAL_REVIEW", _risk(score=101))])
		self.assertEqual(frappe.db.get_value(_REVIEW, "R1", "risk_score"), 101)

	def test_non_int_score_row_kept_degraded(self):
		# A non-int score (a contract violation already warned by G1) must not lose the row.
		# Frappe Int fields are non-nullable and default to 0 — degraded but never a crash.
		self._push([_item("R1", "MANUAL_REVIEW", _risk(score="not-a-number"))])
		self.assertEqual(frappe.db.count(_REVIEW), 1)  # row kept
		self.assertEqual(frappe.db.get_value(_REVIEW, "R1", "risk_score"), 0)

	# ---- read API shapes ---------------------------------------------------
	def test_review_queue_state_shape(self):
		self._push([_item("R1", "MANUAL_REVIEW", _risk())])
		state = review.review_queue_state()
		self.assertTrue(state["permitted"])
		self.assertEqual(state["count"], 1)
		item = state["items"][0]
		self.assertEqual(item["ref"], "R1")
		self.assertEqual(item["kes_display"], "KES 95,000")
		self.assertEqual(item["score"], 78)
		self.assertEqual(item["band"], "REVIEW")
		self.assertEqual(item["band_class"], "review")
		self.assertIn("Tier-1", item["top_reason"])  # top contribution row's reason

	def test_review_item_detail_shape(self):
		self._push([_item("R1", "MANUAL_REVIEW", _risk())])
		d = review.review_item_detail("R1")
		self.assertTrue(d["permitted"])
		self.assertEqual(d["ref"], "R1")
		self.assertEqual(d["score"], 78)
		self.assertEqual(d["band_class"], "review")
		self.assertEqual(d["scorer_caption"], "Scored by engine v1")
		self.assertIn("amount_vs_kyc_tier", d["breakdown_html"])
		self.assertIn("KES 95,000", d["breakdown_html"])

	def test_review_item_detail_missing_returns_found_false(self):
		d = review.review_item_detail("DOES-NOT-EXIST")
		self.assertTrue(d["permitted"])
		self.assertFalse(d["found"])

	# ---- server-side permission gate (real role matrix lives in G4) --------
	def test_no_read_permission_returns_not_permitted(self):
		self._push([_item("R1", "MANUAL_REVIEW", _risk())])
		with patch.object(frappe, "has_permission", return_value=False):
			state = review.review_queue_state()
			detail = review.review_item_detail("R1")
		self.assertFalse(state["permitted"])
		self.assertEqual(state["items"], [])
		self.assertFalse(detail["permitted"])

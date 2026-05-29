"""Integration tests for the Phase-2 mirror receive endpoints.

Exercises the whitelisted handlers in-process with a faked signed request: storage,
snapshot-overwrite (each push replaces the last), the warn-and-store PII guard, and
schema-validation rejections. `frappe.db.commit` is patched to a no-op so each test
stays inside the IntegrationTestCase transaction and rolls back cleanly.
"""

import json
import time
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness import verify as V
from harness.koya_harness.api import mirrors
from harness.koya_harness.sign import compute_signature

TEST_SECRET = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
_RATE = "Koya Rate Mirror"
_TXN = "Koya Transaction Mirror"


class FakeReq:
	def __init__(self, headers: dict, body: bytes):
		self.headers = headers
		self._body = body

	def get_data(self) -> bytes:
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


def _rates_body(source="binance", request_id=None):
	return {
		"request_id": request_id or str(uuid.uuid4()),
		"schema_version": 1,
		"snapshot_at": "2026-05-29T12:34:56.789Z",
		"rates": [
			{
				"asset": "BTC",
				"pair": "BTC/KES",
				"mid_rate": "5234567.89",
				"buy_rate": "5260000.00",
				"sell_rate": "5210000.00",
				"spread_pct": "1.50",
				"source": source,
				"fetched_at": "2026-05-29T12:34:55.123Z",
				"stale": False,
			}
		],
	}


def _txn_body(ref="KYA-2026-05-29-0001", with_pii=False):
	item = {
		"ref": ref,
		"state": "COMPLETED",
		"asset": "BTC",
		"created_at": "2026-05-29T12:30:11.000Z",
		"updated_at": "2026-05-29T12:33:47.000Z",
		"kes_amount": "10000.00",
		"asset_amount": "0.00191",
		"txid": "c3f45565c96866717d2890e7cc5cd0459f6b36a080007cf09d48d760903cb24a",
	}
	if with_pii:
		item["email"] = "leaked@example.com"
	return {
		"request_id": str(uuid.uuid4()),
		"schema_version": 1,
		"snapshot_at": "2026-05-29T12:34:56.789Z",
		"status_counts": {"COMPLETED": 47, "MANUAL_REVIEW": 2, "FAILED": 4},
		"recent": [item],
		"recent_count": 50,
	}


class TestMirrors(IntegrationTestCase):
	def setUp(self):
		frappe.local.response = frappe._dict()
		p1 = patch.object(V, "get_outbound_secret", return_value=TEST_SECRET)
		p2 = patch.object(frappe.db, "commit")  # keep writes inside the test transaction
		p1.start()
		p2.start()
		self.addCleanup(p1.stop)
		self.addCleanup(p2.stop)

	def _call(self, fn, body: dict) -> dict:
		raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
		frappe.local.request = FakeReq(_signed_headers(raw), raw)
		frappe.local.response = frappe._dict()
		return fn()

	# ---- storage -----------------------------------------------------------
	def test_valid_rates_push_stored(self):
		body = _rates_body()
		res = self._call(mirrors.rates, body)
		self.assertTrue(res["ok"])
		self.assertEqual(frappe.db.get_single_value(_RATE, "request_id"), body["request_id"])
		self.assertIsNotNone(frappe.db.get_single_value(_RATE, "received_at"))
		self.assertEqual(frappe.db.get_single_value(_RATE, "last_source"), "binance")
		self.assertEqual(frappe.db.get_single_value(_RATE, "schema_version"), 1)

	def test_valid_transactions_push_stored(self):
		body = _txn_body()
		res = self._call(mirrors.transactions, body)
		self.assertTrue(res["ok"])
		self.assertEqual(frappe.db.get_single_value(_TXN, "request_id"), body["request_id"])
		self.assertEqual(frappe.db.get_single_value(_TXN, "recent_count"), 50)
		counts = json.loads(frappe.db.get_single_value(_TXN, "status_counts_json"))
		self.assertEqual(counts["COMPLETED"], 47)
		recent = json.loads(frappe.db.get_single_value(_TXN, "recent_json"))
		self.assertEqual(recent[0]["ref"], "KYA-2026-05-29-0001")

	# ---- PII guard ---------------------------------------------------------
	def test_pii_guard_warns_and_stores(self):
		body = _txn_body(ref="KYA-2026-05-29-0099", with_pii=True)
		res = self._call(mirrors.transactions, body)
		self.assertTrue(res["ok"])  # stored, NOT rejected
		warning = frappe.db.get_single_value(_TXN, "pii_warning")
		self.assertIn("email", warning)
		self.assertNotIn("leaked@example.com", warning or "")  # key name only, never the value
		recent = json.loads(frappe.db.get_single_value(_TXN, "recent_json"))
		self.assertEqual(recent[0]["ref"], "KYA-2026-05-29-0099")

	# ---- snapshot overwrite ------------------------------------------------
	def test_second_push_overwrites(self):
		first = _rates_body(source="binance")
		self._call(mirrors.rates, first)
		second = _rates_body(source="coingecko")
		self._call(mirrors.rates, second)
		self.assertEqual(frappe.db.get_single_value(_RATE, "request_id"), second["request_id"])
		self.assertEqual(frappe.db.get_single_value(_RATE, "last_source"), "coingecko")
		stored = json.loads(frappe.db.get_single_value(_RATE, "rates_json"))
		self.assertEqual(stored, second["rates"])

	# ---- schema validation -------------------------------------------------
	def test_rates_missing_schema_version(self):
		body = _rates_body()
		del body["schema_version"]
		res = self._call(mirrors.rates, body)
		self.assertFalse(res["ok"])
		self.assertEqual(res["error"]["code"], "validation_error")
		self.assertEqual(frappe.local.response["http_status_code"], 400)

	def test_rates_bad_decimal(self):
		body = _rates_body()
		body["rates"][0]["mid_rate"] = "not-a-number"
		res = self._call(mirrors.rates, body)
		self.assertFalse(res["ok"])
		self.assertEqual(res["error"]["code"], "validation_error")

	def test_rates_not_array(self):
		body = _rates_body()
		body["rates"] = {"oops": 1}
		res = self._call(mirrors.rates, body)
		self.assertFalse(res["ok"])
		self.assertEqual(res["error"]["code"], "validation_error")

	def test_txn_missing_status_counts(self):
		body = _txn_body()
		del body["status_counts"]
		res = self._call(mirrors.transactions, body)
		self.assertFalse(res["ok"])
		self.assertEqual(res["error"]["code"], "validation_error")

	def test_forged_signature_rejected(self):
		body = _rates_body()
		raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
		h = _signed_headers(raw)
		s = h["X-Harness-Signature"]
		h["X-Harness-Signature"] = s[:-1] + ("0" if s[-1] != "0" else "1")
		frappe.local.request = FakeReq(h, raw)
		frappe.local.response = frappe._dict()
		res = mirrors.rates()
		self.assertFalse(res["ok"])
		self.assertEqual(res["error"]["code"], "signature_mismatch")
		self.assertEqual(frappe.local.response["http_status_code"], 401)

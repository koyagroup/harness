"""G6 — inbound health-ping receiver.

Symmetric to Phase 1's Koya-side ping: HMAC-verified with the SAME outbound secret and the
SAME `harness:outbound-nonce:` replay keyspace as the mirror endpoints. Valid → 200 + echo;
forged → 401 signature_mismatch; replay → 401 nonce_replay.
"""

import json
import time
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness import verify as V
from harness.koya_harness.api import health
from harness.koya_harness.sign import compute_signature

TEST_SECRET = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
_AUDIT = "Koya Harness Audit Log"


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


class TestHealthPing(IntegrationTestCase):
	def setUp(self):
		frappe.local.response = frappe._dict()
		p1 = patch.object(V, "get_outbound_secret", return_value=TEST_SECRET)
		p2 = patch.object(frappe.db, "commit")
		p1.start()
		p2.start()
		self.addCleanup(p1.stop)
		self.addCleanup(p2.stop)

	def _call(self, headers, raw):
		frappe.local.request = FakeReq(headers, raw)
		frappe.local.response = frappe._dict()
		return health.ping()

	def _signed(self, body: dict):
		raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
		return _signed_headers(raw), raw

	def test_valid_ping_echoes(self):
		headers, raw = self._signed({"echo": "hi"})
		res = self._call(headers, raw)
		self.assertTrue(res["ok"])
		self.assertEqual(res["data"]["echo"], "hi")
		self.assertEqual(len(res["data"]["harness_request_id"]), 36)  # uuid4
		self.assertTrue(res["data"]["received_at"].endswith("Z"))

	def test_empty_echo_ok(self):
		headers, raw = self._signed({})  # non-empty body, no echo key
		res = self._call(headers, raw)
		self.assertTrue(res["ok"])
		self.assertIsNone(res["data"]["echo"])

	def test_non_string_echo_rejected(self):
		headers, raw = self._signed({"echo": 123})
		res = self._call(headers, raw)
		self.assertFalse(res["ok"])
		self.assertEqual(res["error"]["code"], "validation_error")
		self.assertEqual(frappe.local.response["http_status_code"], 400)

	def test_forged_signature_401(self):
		headers, raw = self._signed({"echo": "hi"})
		s = headers["X-Harness-Signature"]
		headers["X-Harness-Signature"] = s[:-1] + ("0" if s[-1] != "0" else "1")
		res = self._call(headers, raw)
		self.assertFalse(res["ok"])
		self.assertEqual(res["error"]["code"], "signature_mismatch")
		self.assertEqual(frappe.local.response["http_status_code"], 401)

	def test_replay_401(self):
		headers, raw = self._signed({"echo": "hi"})  # fixed nonce reused across both calls
		first = self._call(headers, raw)
		self.assertTrue(first["ok"])
		second = self._call(headers, raw)
		self.assertFalse(second["ok"])
		self.assertEqual(second["error"]["code"], "nonce_replay")
		self.assertEqual(frappe.local.response["http_status_code"], 401)

	def test_ping_writes_audit_row(self):
		headers, raw = self._signed({"echo": "hi"})
		res = self._call(headers, raw)
		hrid = res["data"]["harness_request_id"]
		rows = frappe.get_all(
			_AUDIT, filters={"harness_request_id": hrid}, fields=["event_type", "detail_json"]
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].event_type, "health_ping_received")
		self.assertNotIn("hi", rows[0].detail_json)  # echo value never logged

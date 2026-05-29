"""Unit tests for the Phase-2 inbound mirror verifier.

Mirrors the Phase-1 signer test discipline. The reference-vector test is THE gate: the
same Appendix-A inputs that the Phase-1 signer reproduces must be *accepted* by the
verifier when presented as the outbound secret. The rest of the matrix proves every
rejection path in Wire Contract v1 §2, plus the sign-what-you-send invariant in reverse
(a re-serialized body must fail).
"""

import json
import time
import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness import verify as V
from harness.koya_harness.sign import compute_signature

TEST_SECRET = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
REF_TS = "1716894732"
REF_NONCE = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
REF_BODY = b'{"echo":"hello"}'
REF_SIG = "f069372aa1da0d209b44cce51493c237214abf0eb7e02955741ceb3679c8d996"


class FakeReq:
	"""Minimal stand-in for a Werkzeug request: case-sensitive dict headers + raw bytes."""

	def __init__(self, headers: dict, body: bytes):
		self.headers = headers
		self._body = body

	def get_data(self) -> bytes:
		return self._body


def _headers(raw, secret=TEST_SECRET, ts=None, nonce=None, ctype="application/json"):
	ts = ts if ts is not None else str(int(time.time()))
	nonce = nonce or str(uuid.uuid4()).lower()
	h = {
		"X-Harness-Timestamp": ts,
		"X-Harness-Nonce": nonce,
		"X-Harness-Signature": compute_signature(secret, ts, nonce, raw),
	}
	if ctype is not None:
		h["Content-Type"] = ctype
	return h


@patch.object(V, "get_outbound_secret", return_value=TEST_SECRET)
class TestVerify(IntegrationTestCase):
	def _verify(self, headers, body):
		return V.verify_outbound_signed_request(FakeReq(headers, body))

	# ---- THE gate ----------------------------------------------------------
	def test_reference_vector_accepts(self, _mock):
		# The reference vector uses a FIXED nonce; clear any prior recording so the
		# real Redis replay store (TTL 600s) doesn't fail this across back-to-back runs.
		# Use raw .delete() (not delete_value, which site-prefixes) to match the raw
		# .set() the verifier uses for the atomic SET NX EX.
		frappe.cache().delete(f"{V._NONCE_PREFIX}{REF_NONCE}")
		# The signer and verifier must agree on the Appendix-A hex.
		self.assertEqual(compute_signature(TEST_SECRET, REF_TS, REF_NONCE, REF_BODY), REF_SIG)
		headers = {
			"X-Harness-Timestamp": REF_TS,
			"X-Harness-Nonce": REF_NONCE,
			"X-Harness-Signature": REF_SIG,
			"Content-Type": "application/json",
		}
		# Pin clock inside the skew window of the (historical) reference timestamp.
		with patch.object(V.time, "time", return_value=int(REF_TS) + 1):
			ok, res = self._verify(headers, REF_BODY)
		self.assertTrue(ok)
		self.assertEqual(res["raw_body"], REF_BODY)
		self.assertIn("correlation_id", res)

	def test_valid_fresh_request_accepts(self, _mock):
		raw = b'{"snapshot_at":"x","rates":[]}'
		ok, _res = self._verify(_headers(raw), raw)
		self.assertTrue(ok)

	# ---- crypto rejections -------------------------------------------------
	def test_wrong_signature(self, _mock):
		raw = b'{"x":1}'
		h = _headers(raw)
		s = h["X-Harness-Signature"]
		h["X-Harness-Signature"] = s[:-1] + ("0" if s[-1] != "0" else "1")
		ok, res = self._verify(h, raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "signature_mismatch")
		self.assertEqual(res["http_status"], 401)

	def test_nonce_replay(self, _mock):
		raw = b'{"x":1}'
		h = _headers(raw)
		ok1, _r = self._verify(h, raw)
		self.assertTrue(ok1)
		ok2, res = self._verify(h, raw)  # identical nonce
		self.assertFalse(ok2)
		self.assertEqual(res["error"]["code"], "nonce_replay")

	def test_stale_timestamp(self, _mock):
		raw = b'{"x":1}'
		ok, res = self._verify(_headers(raw, ts=str(int(time.time()) - 3600)), raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "timestamp_skew")

	def test_future_timestamp(self, _mock):
		raw = b'{"x":1}'
		ok, res = self._verify(_headers(raw, ts=str(int(time.time()) + 3600)), raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "timestamp_skew")

	# ---- structural rejections ---------------------------------------------
	def test_missing_each_header(self, _mock):
		raw = b'{"x":1}'
		for drop in ("X-Harness-Timestamp", "X-Harness-Nonce", "X-Harness-Signature"):
			h = _headers(raw)
			del h[drop]
			ok, res = self._verify(h, raw)
			self.assertFalse(ok)
			self.assertEqual(res["error"]["code"], "missing_required_headers", drop)

	def test_malformed_signature_uppercase(self, _mock):
		raw = b'{"x":1}'
		h = _headers(raw)
		h["X-Harness-Signature"] = h["X-Harness-Signature"].upper()
		ok, res = self._verify(h, raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "malformed_signature_headers")

	def test_malformed_signature_wrong_length(self, _mock):
		raw = b'{"x":1}'
		h = _headers(raw)
		h["X-Harness-Signature"] = "abc123"
		ok, res = self._verify(h, raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "malformed_signature_headers")

	def test_malformed_nonce(self, _mock):
		raw = b'{"x":1}'
		h = _headers(raw)
		h["X-Harness-Nonce"] = "not-a-uuid"
		ok, res = self._verify(h, raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "malformed_signature_headers")

	def test_unsupported_content_type(self, _mock):
		raw = b'{"x":1}'
		ok, res = self._verify(_headers(raw, ctype="text/plain"), raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "unsupported_content_type")

	def test_charset_suffix_tolerated(self, _mock):
		raw = b'{"x":1}'
		ok, _res = self._verify(_headers(raw, ctype="application/json; charset=utf-8"), raw)
		self.assertTrue(ok)

	def test_empty_body(self, _mock):
		raw = b""
		ok, res = self._verify(_headers(raw), raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "empty_body")

	def test_body_too_large(self, _mock):
		raw = b'{"x":"' + b"a" * (256 * 1024) + b'"}'
		ok, res = self._verify(_headers(raw), raw)
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "body_too_large")

	# ---- verify-what-you-received invariant --------------------------------
	def test_reserialized_body_fails(self, _mock):
		raw = b'{"a":1,"b":2}'  # compact, as Koya would send
		reserialized = json.dumps(json.loads(raw)).encode("utf-8")  # adds spaces -> different bytes
		self.assertNotEqual(raw, reserialized)
		h = _headers(reserialized)  # sign the re-serialized copy
		ok, res = self._verify(h, raw)  # but send the original bytes
		self.assertFalse(ok)
		self.assertEqual(res["error"]["code"], "signature_mismatch")

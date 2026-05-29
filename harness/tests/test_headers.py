import unittest

from harness.koya_harness.headers import build_signed_request
from harness.koya_harness.sign import compute_signature


class TestBuildSignedRequest(unittest.TestCase):
	def test_signature_in_headers_matches_raw_body_bytes(self):
		"""The signature in headers must verify against the exact bytes returned."""
		secret = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
		raw_body, headers = build_signed_request(secret, {"echo": "hi"})
		recomputed = compute_signature(
			secret,
			headers["X-Harness-Timestamp"],
			headers["X-Harness-Nonce"],
			raw_body,
		)
		self.assertEqual(headers["X-Harness-Signature"], recomputed)

	def test_fresh_nonce_per_call(self):
		secret = "x"
		_, h1 = build_signed_request(secret, {"echo": "a"})
		_, h2 = build_signed_request(secret, {"echo": "a"})
		self.assertNotEqual(h1["X-Harness-Nonce"], h2["X-Harness-Nonce"])

	def test_required_headers_present(self):
		_, h = build_signed_request("x", {"echo": "a"})
		for required in (
			"Content-Type",
			"X-Harness-Timestamp",
			"X-Harness-Nonce",
			"X-Harness-Signature",
		):
			self.assertIn(required, h)
		self.assertEqual(h["Content-Type"], "application/json")

	def test_header_format_invariants(self):
		_, h = build_signed_request("x", {"echo": "a"})
		ts = h["X-Harness-Timestamp"]
		nonce = h["X-Harness-Nonce"]
		sig = h["X-Harness-Signature"]

		self.assertTrue(ts.isdigit(), "timestamp must be ASCII digits only")
		self.assertEqual(len(nonce), 36, "nonce must be canonical UUID v4 (36 chars)")
		self.assertEqual(nonce, nonce.lower(), "nonce must be lowercase")
		self.assertEqual(len(sig), 64, "signature must be 64 hex chars")
		self.assertEqual(sig, sig.lower(), "signature must be lowercase hex")
		int(sig, 16)  # raises if not hex

	def test_compact_json_for_reference_vector_payload(self):
		"""Sanity: build_signed_request produces 16-byte body for {"echo":"hello"}."""
		raw_body, _ = build_signed_request("x", {"echo": "hello"})
		self.assertEqual(raw_body, b'{"echo":"hello"}')
		self.assertEqual(len(raw_body), 16)


if __name__ == "__main__":
	unittest.main()

import unittest

from harness.koya_harness.sign import compute_signature


class TestReferenceVector(unittest.TestCase):
	"""Appendix-A reference vector — verified Python/Node byte-identical.

	If this fails, the bug is ours. Check, in order:
	  (a) signing the raw bytes, not a re-serialized object
	  (b) concat order: ts + "." + nonce + "." + raw_body
	  (c) lowercase hex output
	"""

	def test_appendix_a_vector(self):
		secret = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
		ts = "1716894732"
		nonce = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
		raw_body = b'{"echo":"hello"}'
		expected = "f069372aa1da0d209b44cce51493c237214abf0eb7e02955741ceb3679c8d996"

		self.assertEqual(len(raw_body), 16, "reference body must be exactly 16 bytes")
		sig = compute_signature(secret, ts, nonce, raw_body)
		self.assertEqual(sig, expected)
		self.assertEqual(len(sig), 64)
		self.assertEqual(sig, sig.lower())


if __name__ == "__main__":
	unittest.main()

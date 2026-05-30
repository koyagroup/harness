import unittest
from unittest.mock import MagicMock, patch

import requests

from harness.koya_harness import client


class TestRetryBehavior(unittest.TestCase):
	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_retry_uses_fresh_nonce_on_signature_mismatch(self, mock_post, *_):
		fail = MagicMock(status_code=401)
		fail.json.return_value = {
			"ok": False,
			"error": {"code": "signature_mismatch", "message": "x"},
		}
		ok = MagicMock(status_code=200)
		ok.json.return_value = {"ok": True, "data": {"echo": "hi"}}
		mock_post.side_effect = [fail, ok]

		result = client.post_signed("/internal/harness/ping", {"echo": "hi"})

		self.assertEqual(result, {"ok": True, "data": {"echo": "hi"}})
		self.assertEqual(mock_post.call_count, 2)
		nonce_first = mock_post.call_args_list[0].kwargs["headers"]["X-Harness-Nonce"]
		nonce_second = mock_post.call_args_list[1].kwargs["headers"]["X-Harness-Nonce"]
		self.assertNotEqual(nonce_first, nonce_second)

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_retry_cap_is_bounded(self, mock_post, *_):
		fail = MagicMock(status_code=401)
		fail.json.return_value = {
			"ok": False,
			"error": {"code": "signature_mismatch", "message": "x"},
		}
		mock_post.return_value = fail

		result = client.post_signed("/internal/harness/ping", {"echo": "hi"})

		self.assertEqual(mock_post.call_count, 3)
		self.assertEqual(result["ok"], False)

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_non_retryable_401_returns_immediately(self, mock_post, *_):
		fail = MagicMock(status_code=401)
		fail.json.return_value = {
			"ok": False,
			"error": {"code": "missing_required_headers", "message": "x"},
		}
		mock_post.return_value = fail

		result = client.post_signed("/internal/harness/ping", {"echo": "hi"})

		self.assertEqual(mock_post.call_count, 1)
		self.assertEqual(result["error"]["code"], "missing_required_headers")

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_request_uses_raw_body_not_json_param(self, mock_post, *_):
		"""Critical: caller must pass the raw signed bytes via data=, not json=."""
		ok = MagicMock(status_code=200)
		ok.json.return_value = {"ok": True, "data": {}}
		mock_post.return_value = ok

		client.post_signed("/internal/harness/ping", {"echo": "hi"})

		call = mock_post.call_args
		self.assertIn("data", call.kwargs)
		self.assertNotIn("json", call.kwargs)
		self.assertIsInstance(call.kwargs["data"], bytes)

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_connection_error_returns_transport_error_envelope(self, mock_post, *_):
		mock_post.side_effect = requests.ConnectionError("refused")

		result = client.post_signed("/internal/harness/ping", {"echo": "hi"})

		self.assertEqual(result["ok"], False)
		self.assertEqual(result["error"]["code"], "transport_error")
		self.assertEqual(mock_post.call_count, 1)

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_timeout_returns_transport_error_envelope(self, mock_post, *_):
		mock_post.side_effect = requests.Timeout("timed out")

		result = client.post_signed("/internal/harness/ping", {"echo": "hi"})

		self.assertEqual(result["error"]["code"], "transport_error")


class TestWithStatus(unittest.TestCase):
	"""Phase-4 opt-in: post_signed(..., with_status=True) returns (body, http_status). The
	default (no flag) MUST still return the bare body dict — Phase-1 callers depend on it."""

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_default_return_is_bare_dict(self, mock_post, *_):
		ok = MagicMock(status_code=200)
		ok.json.return_value = {"ok": True, "data": {"resulting_state": "PAYMENT_PENDING"}}
		mock_post.return_value = ok
		result = client.post_signed("/internal/harness/settlement-decision", {"x": 1})
		self.assertEqual(result, {"ok": True, "data": {"resulting_state": "PAYMENT_PENDING"}})

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_with_status_returns_tuple_on_200(self, mock_post, *_):
		ok = MagicMock(status_code=200)
		ok.json.return_value = {"ok": True, "data": {}}
		mock_post.return_value = ok
		body, status = client.post_signed("/p", {"x": 1}, with_status=True)
		self.assertEqual(status, 200)
		self.assertTrue(body["ok"])

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_with_status_surfaces_409(self, mock_post, *_):
		conflict = MagicMock(status_code=409)
		conflict.json.return_value = {"ok": False, "error": {"code": "conflict"}}
		mock_post.return_value = conflict
		body, status = client.post_signed("/p", {"x": 1}, with_status=True)
		self.assertEqual(status, 409)
		self.assertEqual(body["error"]["code"], "conflict")

	@patch("harness.koya_harness.client.get_inbound_secret", return_value="s")
	@patch("harness.koya_harness.client.get_koya_base_url", return_value="https://koya.test")
	@patch("harness.koya_harness.client.requests.post")
	def test_with_status_transport_error_status_none(self, mock_post, *_):
		mock_post.side_effect = requests.ConnectionError("refused")
		body, status = client.post_signed("/p", {"x": 1}, with_status=True)
		self.assertIsNone(status)
		self.assertEqual(body["error"]["code"], "transport_error")


if __name__ == "__main__":
	unittest.main()

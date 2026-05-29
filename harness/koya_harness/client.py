import requests

from harness.koya_harness.config import get_inbound_secret, get_koya_base_url
from harness.koya_harness.headers import build_signed_request

_RETRYABLE_ERROR_CODES = {"signature_mismatch", "nonce_replay", "timestamp_skew"}
_MAX_RETRIES = 2
_TIMEOUT_SECONDS = 10


def post_signed(path: str, payload: dict) -> dict:
	"""POST `payload` to Koya at `path` with a signed envelope.

	Retries up to _MAX_RETRIES times on 401 with a retryable error code,
	rebuilding headers each time so each attempt has a fresh timestamp and a
	fresh nonce. Returns the parsed JSON response (success OR error envelope).
	"""
	secret = get_inbound_secret()
	url = f"{get_koya_base_url()}{path}"

	last_response = None
	for _ in range(_MAX_RETRIES + 1):
		raw_body, headers = build_signed_request(secret, payload)
		try:
			resp = requests.post(url, data=raw_body, headers=headers, timeout=_TIMEOUT_SECONDS)
		except requests.RequestException as e:
			return {
				"ok": False,
				"error": {
					"code": "transport_error",
					"message": type(e).__name__,
					"request_id": None,
				},
			}
		last_response = resp
		if resp.status_code == 200:
			return resp.json()
		if resp.status_code == 401:
			try:
				body = resp.json()
			except ValueError:
				break
			code = (body.get("error") or {}).get("code")
			if code in _RETRYABLE_ERROR_CODES:
				continue
			return body
		break

	try:
		return last_response.json()
	except ValueError, AttributeError:
		return {
			"ok": False,
			"error": {
				"code": "transport_error",
				"message": f"HTTP {getattr(last_response, 'status_code', 'n/a')}",
				"request_id": None,
			},
		}

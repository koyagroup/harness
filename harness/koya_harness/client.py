import requests

from harness.koya_harness.config import get_inbound_secret, get_koya_base_url
from harness.koya_harness.headers import build_signed_request

_RETRYABLE_ERROR_CODES = {"signature_mismatch", "nonce_replay", "timestamp_skew"}
_MAX_RETRIES = 2
_TIMEOUT_SECONDS = 10


def post_signed(path: str, payload: dict, with_status: bool = False):
	"""POST `payload` to Koya at `path` with a signed envelope.

	Retries up to _MAX_RETRIES times on 401 with a retryable error code, rebuilding
	headers each time so each attempt has a fresh timestamp and a fresh nonce. Returns the
	parsed JSON response (success OR error envelope).

	When `with_status` is True, returns a `(body, http_status)` tuple instead — `http_status`
	is None for a transport-level failure (no response was received). Existing callers omit
	the flag and get the bare body dict, unchanged (Phase 4 opts in so it can branch on the
	HTTP status, which the body alone does not always carry).
	"""
	secret = get_inbound_secret()
	url = f"{get_koya_base_url()}{path}"

	def _ret(body, status):
		return (body, status) if with_status else body

	last_response = None
	for _ in range(_MAX_RETRIES + 1):
		raw_body, headers = build_signed_request(secret, payload)
		try:
			resp = requests.post(url, data=raw_body, headers=headers, timeout=_TIMEOUT_SECONDS)
		except requests.RequestException as e:
			return _ret(
				{
					"ok": False,
					"error": {
						"code": "transport_error",
						"message": type(e).__name__,
						"request_id": None,
					},
				},
				None,
			)
		last_response = resp
		if resp.status_code == 200:
			return _ret(resp.json(), 200)
		if resp.status_code == 401:
			try:
				body = resp.json()
			except ValueError:
				break
			code = (body.get("error") or {}).get("code")
			if code in _RETRYABLE_ERROR_CODES:
				continue
			return _ret(body, 401)
		break

	status = getattr(last_response, "status_code", None)
	try:
		return _ret(last_response.json(), status)
	except ValueError, AttributeError:
		return _ret(
			{
				"ok": False,
				"error": {
					"code": "transport_error",
					"message": f"HTTP {status if status is not None else 'n/a'}",
					"request_id": None,
				},
			},
			status,
		)

"""Inbound verifier for Koya→harness display-mirror pushes (Phase 2).

Mirror of the Phase-1 signer: same HMAC scheme (`ts + "." + nonce + "." + rawBody`,
HMAC-SHA256, lowercase 64-hex), only the *direction of comparison* differs. We REUSE
`compute_signature` from `sign.py` — no HMAC code is duplicated here — and verify the
result with `hmac.compare_digest` (constant-time, no timing oracle).

The verification order is load-bearing: cheap structural checks first, crypto next, the
Redis replay round-trip last. This matches Wire Contract v1 §2.

The rawBody used for the HMAC is the *literal request bytes as received*
(`request.get_data()`), NEVER a parsed-then-reserialized object — the verify-what-you-
received counterpart to the signer's sign-what-you-send discipline.
"""

import hmac
import re
import time
import uuid

import frappe

from harness.koya_harness.config import get_outbound_secret
from harness.koya_harness.log import get_logger
from harness.koya_harness.sign import compute_signature

_TS_HEADER = "X-Harness-Timestamp"
_NONCE_HEADER = "X-Harness-Nonce"
_SIG_HEADER = "X-Harness-Signature"

_MAX_BODY_BYTES = 256 * 1024
_SKEW_PAST = 300
_SKEW_FUTURE = 30

# Replay store: distinct keyspace from any Phase-1 inbound nonce store.
_NONCE_PREFIX = "harness:outbound-nonce:"
_NONCE_TTL = 600

_TS_RE = re.compile(r"^[0-9]+$")
_NONCE_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SIG_RE = re.compile(r"^[0-9a-f]{64}$")


def _log(msg: str) -> None:
	"""Lazy logger — resolved per call so module import never needs a site context."""
	get_logger().info(msg)


def _envelope(code: str, message: str, http_status: int, correlation_id: str) -> dict:
	"""A Wire Contract v1 §6 error envelope plus the HTTP status to set."""
	return {
		"ok": False,
		"http_status": http_status,
		"error": {
			"code": code,
			"message": message,
			"request_id": correlation_id,
		},
	}


def verify_outbound_signed_request(request) -> tuple[bool, dict]:
	"""Verify an inbound mirror push. Returns (ok, result).

	On success: (True, {"raw_body": bytes, "correlation_id": str}).
	On failure: (False, <§6 envelope dict with an extra "http_status" key>).

	`request` is the Werkzeug request (`frappe.local.request`). A fresh harness-side
	correlation id is minted per call for cross-system log correlation; the caller logs
	it alongside the body's Koya-minted request_id once the body is parsed.
	"""
	correlation_id = str(uuid.uuid4())

	# 1. All three headers present.
	ts = request.headers.get(_TS_HEADER)
	nonce = request.headers.get(_NONCE_HEADER)
	sig = request.headers.get(_SIG_HEADER)
	if not (ts and nonce and sig):
		_log(f"mirror reject missing_required_headers cid={correlation_id}")
		return False, _envelope(
			"missing_required_headers", "Missing one or more signature headers.", 400, correlation_id
		)

	# 2. Header format.
	if not (_TS_RE.match(ts) and _NONCE_RE.match(nonce) and _SIG_RE.match(sig)):
		_log(f"mirror reject malformed_signature_headers cid={correlation_id}")
		return False, _envelope(
			"malformed_signature_headers", "Malformed signature header(s).", 400, correlation_id
		)

	# 3. Content-Type + body presence/size.
	content_type = (request.headers.get("Content-Type") or "").split(";")[0].strip().lower()
	if content_type != "application/json":
		return False, _envelope(
			"unsupported_content_type", "Content-Type must be application/json.", 400, correlation_id
		)
	raw_body = request.get_data()
	if not raw_body:
		return False, _envelope("empty_body", "Request body is empty.", 400, correlation_id)
	if len(raw_body) > _MAX_BODY_BYTES:
		return False, _envelope("body_too_large", "Request body exceeds 256KB.", 400, correlation_id)

	# 4. Timestamp skew (now-300 <= ts <= now+30).
	now = int(time.time())
	ts_int = int(ts)
	if ts_int < now - _SKEW_PAST or ts_int > now + _SKEW_FUTURE:
		_log(f"mirror reject timestamp_skew cid={correlation_id}")
		return False, _envelope(
			"timestamp_skew", "Timestamp outside the accepted skew window.", 401, correlation_id
		)

	# 5. Signature — constant-time compare against the secret read at REQUEST time.
	expected = compute_signature(get_outbound_secret(), ts, nonce, raw_body)
	if not hmac.compare_digest(expected, sig):
		_log(f"mirror reject signature_mismatch cid={correlation_id}")
		return False, _envelope("signature_mismatch", "Signature verification failed.", 401, correlation_id)

	# 6. Atomic replay guard: SET key 1 NX EX 600. Falsy => key already present => replay.
	fresh = frappe.cache().set(f"{_NONCE_PREFIX}{nonce}", "1", ex=_NONCE_TTL, nx=True)
	if not fresh:
		_log(f"mirror reject nonce_replay cid={correlation_id}")
		return False, _envelope("nonce_replay", "Nonce has already been used.", 401, correlation_id)

	# 7. Pass.
	return True, {"raw_body": raw_body, "correlation_id": correlation_id}

import json
import time
import uuid

from harness.koya_harness.sign import compute_signature


def build_signed_request(secret: str, payload: dict) -> tuple[bytes, dict]:
	"""Serialize `payload` ONCE, sign those exact bytes, return (body_to_send, headers).

	The caller MUST send the returned bytes verbatim. Pass them to
	`requests.post(data=raw_body, ...)`, NEVER `json=payload` — that would
	re-serialize and break the signature.
	"""
	raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
	ts = str(int(time.time()))
	nonce = str(uuid.uuid4()).lower()
	signature = compute_signature(secret, ts, nonce, raw_body)
	headers = {
		"Content-Type": "application/json",
		"X-Harness-Timestamp": ts,
		"X-Harness-Nonce": nonce,
		"X-Harness-Signature": signature,
	}
	return raw_body, headers

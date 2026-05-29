"""Phase-1 joint-test driver (harness side).

Drives the four-outcome joint test against the live Koya `/internal/harness/ping`
endpoint and returns the raw responses for paste-back.

Outcomes (in order):
  1. valid       → 200 + §3 success envelope
  2. forged      → 401 + error.code = signature_mismatch
  3. replay      → first request 200, second (same nonce/sig) 401 nonce_replay
  4. skew        → 401 + error.code = timestamp_skew

This file is a verification artifact for Phase 1; it deliberately constructs
bad-signature / replayed / stale requests to prove the channel rejects them.
"""

import json
import time
import uuid

import frappe
import requests

from harness.koya_harness.config import get_inbound_secret, get_koya_base_url
from harness.koya_harness.headers import build_signed_request
from harness.koya_harness.sign import compute_signature

_PATH = "/internal/harness/ping"
_TIMEOUT = 10


def _post(raw_body: bytes, headers: dict) -> dict:
	url = f"{get_koya_base_url()}{_PATH}"
	try:
		resp = requests.post(url, data=raw_body, headers=headers, timeout=_TIMEOUT)
	except requests.RequestException as e:
		return {"status": None, "transport_error": type(e).__name__, "detail": str(e)[:200]}
	try:
		body = resp.json()
	except ValueError:
		body = {"_raw": resp.text[:500]}
	return {"status": resp.status_code, "body": body}


def _case_valid(secret: str) -> dict:
	raw, headers = build_signed_request(secret, {"echo": "joint-test-1-valid"})
	return _post(raw, headers)


def _case_forged(secret: str) -> dict:
	raw, headers = build_signed_request(secret, {"echo": "joint-test-2-forged"})
	sig = headers["X-Harness-Signature"]
	flipped_last = "f" if sig[-1] != "f" else "0"
	headers["X-Harness-Signature"] = sig[:-1] + flipped_last
	return _post(raw, headers)


def _case_replay(secret: str) -> dict:
	raw, headers = build_signed_request(secret, {"echo": "joint-test-3-replay"})
	first = _post(raw, dict(headers))
	second = _post(raw, dict(headers))
	return {"first": first, "second": second}


def _case_skew(secret: str) -> dict:
	raw_body = json.dumps({"echo": "joint-test-4-skew"}, separators=(",", ":"), ensure_ascii=False).encode(
		"utf-8"
	)
	ts = str(int(time.time()) - 3600)
	nonce = str(uuid.uuid4()).lower()
	sig = compute_signature(secret, ts, nonce, raw_body)
	headers = {
		"Content-Type": "application/json",
		"X-Harness-Timestamp": ts,
		"X-Harness-Nonce": nonce,
		"X-Harness-Signature": sig,
	}
	return _post(raw_body, headers)


@frappe.whitelist()
def run_four_outcomes() -> dict:
	secret = get_inbound_secret()
	results = {
		"1_valid": _case_valid(secret),
		"2_forged": _case_forged(secret),
		"3_replay": _case_replay(secret),
		"4_skew": _case_skew(secret),
	}
	return results

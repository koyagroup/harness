"""Inbound health-ping receiver (Phase 3, G6) — the reverse of Phase 1's Koya-side ping.

Koya hits this to check the harness is alive. Auth is the SAME HMAC verification used for
the Phase-2 mirror pushes (`verify_outbound_signed_request` — same outbound secret, same
`harness:outbound-nonce:` replay keyspace), just on a different endpoint. Body is an
optional `{"echo": "<string>"}`. Not wired into any flow yet; the receiver exists for
future bidirectional health checks. Read-only: it verifies, echoes, audits — nothing else.
"""

import datetime
import json
import uuid

import frappe

from harness.koya_harness.api._responses import (
	fail as _fail,
)
from harness.koya_harness.api._responses import (
	internal_error as _internal_error,
)
from harness.koya_harness.api._responses import (
	validation_error as _validation_error,
)
from harness.koya_harness.audit import write_audit
from harness.koya_harness.log import get_logger
from harness.koya_harness.verify import verify_outbound_signed_request


def _rfc3339_now() -> str:
	"""RFC 3339 ms UTC (Z) — symmetric to the contract's timestamp format."""
	now = datetime.datetime.now(datetime.timezone.utc)
	return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


@frappe.whitelist(allow_guest=True)
def ping() -> dict:
	correlation_id = None
	try:
		ok, result = verify_outbound_signed_request(frappe.local.request)
		if not ok:
			return _fail(result)
		correlation_id = result["correlation_id"]

		# Body is optional per the contract; the verifier already guarantees it is
		# non-empty, so we always parse it. An `echo`, if present, must be a string.
		echo = None
		raw = result["raw_body"]
		if raw and raw.strip():
			try:
				body = json.loads(raw)
			except ValueError:
				return _validation_error("Body is not valid JSON.", correlation_id)
			if not isinstance(body, dict):
				return _validation_error("Body must be a JSON object.", correlation_id)
			echo = body.get("echo")
			if echo is not None and not isinstance(echo, str):
				return _validation_error("echo must be a string.", correlation_id)

		harness_request_id = str(uuid.uuid4())
		write_audit(
			"health_ping_received",
			correlation_id=correlation_id,
			harness_request_id=harness_request_id,
			detail={"echo_present": echo is not None},
		)

		get_logger().info(f"health ping accepted cid={correlation_id} hrid={harness_request_id}")
		return {
			"ok": True,
			"data": {
				"echo": echo,
				"received_at": _rfc3339_now(),
				"harness_request_id": harness_request_id,
			},
		}
	except Exception:
		cid = correlation_id or "n/a"
		get_logger().error(f"health ping internal_error cid={cid}")
		return _internal_error(correlation_id or "unknown")

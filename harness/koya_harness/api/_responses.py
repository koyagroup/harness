"""Shared §6-envelope response helpers for the harness inbound endpoints.

Both the Phase-2 mirror receivers and the Phase-3 health-ping receiver return the Wire
Contract §6 envelope and set the authoritative HTTP status on `frappe.local.response`
(Koya keys on the status code; the body is informational). Centralised here so endpoints
share ONE source rather than importing private helpers across modules.
"""

import frappe


def set_status(code: int) -> None:
	frappe.local.response["http_status_code"] = code


def fail(envelope: dict) -> dict:
	"""Strip the internal http_status key, set the HTTP status, return the §6 envelope.

	`envelope` is the failure dict produced by the verifier (has an extra `http_status`).
	"""
	set_status(envelope.get("http_status", 400))
	return {"ok": False, "error": envelope["error"]}


def validation_error(message: str, correlation_id: str) -> dict:
	set_status(400)
	return {
		"ok": False,
		"error": {"code": "validation_error", "message": message, "request_id": correlation_id},
	}


def internal_error(correlation_id: str) -> dict:
	set_status(500)
	return {
		"ok": False,
		"error": {
			"code": "internal_error",
			"message": "Unexpected error handling the request.",
			"request_id": correlation_id,
		},
	}

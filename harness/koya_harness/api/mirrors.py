"""Phase-2 mirror receive endpoints (Koya → harness, one-way display mirrors).

`rates` and `transactions` accept signed snapshot pushes from Koya, verify them with the
outbound secret, and OVERWRITE the corresponding Single doctype (snapshot mode — no
history). `display_state` is the staff-facing read used by the Koya Mirror Status page.

Boundary discipline: this data is READ-ONLY DISPLAY. Nothing here is ever read back as
authoritative for a harness decision — no rate math, no conversion-state logic, no money
path. The endpoints are `allow_guest=True` because Koya authenticates with the HMAC + an
edge IP allowlist, not a Frappe session.

Response shape: the §6 envelope is returned as the method result (Frappe wraps it as
`{"message": <envelope>}`) and the authoritative HTTP status is set on
`frappe.local.response`. Per Wire Contract v1.1 §2.4 Koya keys on the HTTP status code;
the body is informational. Handlers NEVER raise uncaught — any unexpected error becomes a
500 `internal_error` envelope.
"""

import json
from decimal import Decimal, InvalidOperation

import frappe

from harness.koya_harness.log import get_logger
from harness.koya_harness.pii import scan_recent_for_pii
from harness.koya_harness.verify import verify_outbound_signed_request

_RATE_MIRROR = "Koya Rate Mirror"
_TXN_MIRROR = "Koya Transaction Mirror"
_DECIMAL_RATE_FIELDS = ("mid_rate", "buy_rate", "sell_rate", "spread_pct")
_DECIMAL_TXN_FIELDS = ("kes_amount", "asset_amount")


def _log(msg: str) -> None:
	get_logger().info(msg)


def _set_status(code: int) -> None:
	frappe.local.response["http_status_code"] = code


def _fail(envelope: dict) -> dict:
	"""Strip the internal http_status key, set the HTTP status, return the §6 envelope."""
	_set_status(envelope.get("http_status", 400))
	return {"ok": False, "error": envelope["error"]}


def _validation_error(message: str, correlation_id: str) -> dict:
	_set_status(400)
	return {
		"ok": False,
		"error": {"code": "validation_error", "message": message, "request_id": correlation_id},
	}


def _internal_error(correlation_id: str) -> dict:
	_set_status(500)
	return {
		"ok": False,
		"error": {
			"code": "internal_error",
			"message": "Unexpected error handling the mirror push.",
			"request_id": correlation_id,
		},
	}


def _is_decimal_string(value) -> bool:
	if not isinstance(value, str):
		return False
	try:
		Decimal(value)
		return True
	except InvalidOperation:
		return False


def _parse_snapshot_at(value):
	"""Best-effort RFC-3339 → datetime for the informational snapshot_at field."""
	try:
		return frappe.utils.get_datetime(str(value).replace("Z", "+00:00"))
	except Exception:
		return None


# --------------------------------------------------------------------------- rates


@frappe.whitelist(allow_guest=True)
def rates() -> dict:
	correlation_id = None
	try:
		ok, result = verify_outbound_signed_request(frappe.local.request)
		if not ok:
			return _fail(result)
		correlation_id = result["correlation_id"]

		try:
			body = json.loads(result["raw_body"])
		except ValueError:
			return _validation_error("Body is not valid JSON.", correlation_id)

		err = _validate_rates_body(body, correlation_id)
		if err:
			return err

		koya_request_id = body.get("request_id")
		rates_list = body["rates"]
		sources = sorted({r.get("source") for r in rates_list if isinstance(r, dict) and r.get("source")})

		doc = frappe.get_single(_RATE_MIRROR)
		doc.request_id = koya_request_id
		doc.schema_version = body.get("schema_version")
		doc.snapshot_at = _parse_snapshot_at(body.get("snapshot_at"))
		doc.received_at = frappe.utils.now_datetime()
		doc.last_source = ", ".join(sources)
		doc.rates_json = json.dumps(rates_list, separators=(",", ":"))
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		_log(f"mirror rates accepted koya_request_id={koya_request_id} cid={correlation_id}")
		return {"ok": True, "data": {"request_id": correlation_id}}
	except Exception:
		cid = correlation_id or "n/a"
		get_logger().error(f"mirror rates internal_error cid={cid}")
		return _internal_error(correlation_id or "unknown")


def _validate_rates_body(body: dict, correlation_id: str):
	if not isinstance(body, dict):
		return _validation_error("Body must be a JSON object.", correlation_id)
	if not isinstance(body.get("schema_version"), int):
		return _validation_error("schema_version must be an integer.", correlation_id)
	if not body.get("snapshot_at") or not isinstance(body.get("snapshot_at"), str):
		return _validation_error("snapshot_at is required.", correlation_id)
	rates_list = body.get("rates")
	if not isinstance(rates_list, list):
		return _validation_error("rates must be an array.", correlation_id)
	for r in rates_list:
		if not isinstance(r, dict):
			return _validation_error("each rate must be an object.", correlation_id)
		for field in _DECIMAL_RATE_FIELDS:
			if field in r and not _is_decimal_string(r[field]):
				return _validation_error(f"rate {field} must be a decimal string.", correlation_id)
	return None


# -------------------------------------------------------------------- transactions


@frappe.whitelist(allow_guest=True)
def transactions() -> dict:
	correlation_id = None
	try:
		ok, result = verify_outbound_signed_request(frappe.local.request)
		if not ok:
			return _fail(result)
		correlation_id = result["correlation_id"]

		try:
			body = json.loads(result["raw_body"])
		except ValueError:
			return _validation_error("Body is not valid JSON.", correlation_id)

		err = _validate_txn_body(body, correlation_id)
		if err:
			return err

		koya_request_id = body.get("request_id")
		recent = body.get("recent") or []

		# Defense-in-depth PII guard: warn-and-store, never reject (§3.4).
		pii_keys = scan_recent_for_pii(recent)
		pii_warning = None
		if pii_keys:
			pii_warning = "Forbidden PII key(s) present in recent[]: " + ", ".join(pii_keys)
			get_logger().warning(
				f"mirror transactions PII guard tripped keys={pii_keys} "
				f"koya_request_id={koya_request_id} cid={correlation_id}"
			)

		doc = frappe.get_single(_TXN_MIRROR)
		doc.request_id = koya_request_id
		doc.schema_version = body.get("schema_version")
		doc.snapshot_at = _parse_snapshot_at(body.get("snapshot_at"))
		doc.received_at = frappe.utils.now_datetime()
		doc.recent_count = (
			body.get("recent_count") if isinstance(body.get("recent_count"), int) else len(recent)
		)
		doc.pii_warning = pii_warning
		doc.status_counts_json = json.dumps(body.get("status_counts") or {}, separators=(",", ":"))
		doc.recent_json = json.dumps(recent, separators=(",", ":"))
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		_log(f"mirror transactions accepted koya_request_id={koya_request_id} cid={correlation_id}")
		return {"ok": True, "data": {"request_id": correlation_id}}
	except Exception:
		cid = correlation_id or "n/a"
		get_logger().error(f"mirror transactions internal_error cid={cid}")
		return _internal_error(correlation_id or "unknown")


def _validate_txn_body(body: dict, correlation_id: str):
	if not isinstance(body, dict):
		return _validation_error("Body must be a JSON object.", correlation_id)
	if not isinstance(body.get("schema_version"), int):
		return _validation_error("schema_version must be an integer.", correlation_id)
	if not body.get("snapshot_at") or not isinstance(body.get("snapshot_at"), str):
		return _validation_error("snapshot_at is required.", correlation_id)
	if not isinstance(body.get("status_counts"), dict):
		return _validation_error("status_counts must be an object.", correlation_id)
	recent = body.get("recent")
	if not isinstance(recent, list):
		return _validation_error("recent must be an array.", correlation_id)
	for item in recent:
		if not isinstance(item, dict):
			return _validation_error("each recent item must be an object.", correlation_id)
		for field in _DECIMAL_TXN_FIELDS:
			if field in item and not _is_decimal_string(item[field]):
				return _validation_error(f"recent {field} must be a decimal string.", correlation_id)
	return None


# ----------------------------------------------------------------- staff display


@frappe.whitelist()
def display_state() -> dict:
	"""Read-only snapshot of both mirrors + computed staleness, for the status page.

	Staleness threshold = 3x cadence: 90s for rates, 180s for transactions (§5).
	Returns last-good data even when stale (badge, not blank).
	"""
	now = frappe.utils.now_datetime()

	def _age(received_at):
		if not received_at:
			return None
		return int((now - frappe.utils.get_datetime(received_at)).total_seconds())

	rate = frappe.get_single(_RATE_MIRROR)
	txn = frappe.get_single(_TXN_MIRROR)

	rate_age = _age(rate.received_at)
	txn_age = _age(txn.received_at)

	return {
		"server_now": str(now),
		"rates": {
			"request_id": rate.request_id,
			"schema_version": rate.schema_version,
			"snapshot_at": str(rate.snapshot_at) if rate.snapshot_at else None,
			"received_at": str(rate.received_at) if rate.received_at else None,
			"age_seconds": rate_age,
			"stale": rate_age is not None and rate_age > 90,
			"never_received": rate.received_at is None,
			"last_source": rate.last_source,
			"rates": json.loads(rate.rates_json) if rate.rates_json else [],
		},
		"transactions": {
			"request_id": txn.request_id,
			"schema_version": txn.schema_version,
			"snapshot_at": str(txn.snapshot_at) if txn.snapshot_at else None,
			"received_at": str(txn.received_at) if txn.received_at else None,
			"age_seconds": txn_age,
			"stale": txn_age is not None and txn_age > 180,
			"never_received": txn.received_at is None,
			"recent_count": txn.recent_count,
			"pii_warning": txn.pii_warning,
			"status_counts": json.loads(txn.status_counts_json) if txn.status_counts_json else {},
			"recent": json.loads(txn.recent_json) if txn.recent_json else [],
		},
	}

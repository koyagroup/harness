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

from harness.koya_harness.api._responses import (
	fail as _fail,
)
from harness.koya_harness.api._responses import (
	internal_error as _internal_error,
)
from harness.koya_harness.api._responses import (
	set_status as _set_status,
)
from harness.koya_harness.api._responses import (
	validation_error as _validation_error,
)
from harness.koya_harness.audit import write_audit
from harness.koya_harness.log import get_logger
from harness.koya_harness.pii import scan_recent_for_pii
from harness.koya_harness.verify import verify_outbound_signed_request

_RATE_MIRROR = "Koya Rate Mirror"
_TXN_MIRROR = "Koya Transaction Mirror"
_REVIEW_ITEM = "Koya Review Item"
_DECIMAL_RATE_FIELDS = ("mid_rate", "buy_rate", "sell_rate", "spread_pct")
_DECIMAL_TXN_FIELDS = ("kes_amount", "asset_amount")


def _log(msg: str) -> None:
	get_logger().info(msg)


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


# ---------------------------------------------------------------- v2 risk schema
#
# Phase 3 adds an optional `risk` object on MANUAL_REVIEW items in recent[]. The
# receiver tolerates v1 (no `risk` anywhere) and v2 (some items carry `risk`)
# IDENTICALLY — it keys on field presence (`"risk" in item`), NEVER on
# schema_version. Validation is warn-and-store, matching the PII guard: a malformed
# risk object is logged (signal name / stable code only, never values) but the
# snapshot is still stored — Koya is the source of truth.

_KNOWN_RISK_SIGNALS = frozenset(
	{
		"amount_vs_kyc_tier",
		"velocity_count_24h",
		"velocity_volume_24h",
		"first_transaction",
		"destination_reuse_unknown",
		"structuring_pattern",
		"session_anomaly",
	}
)


def _is_int(value) -> bool:
	"""True for a genuine int — bool is a subclass of int and is NOT accepted here."""
	return isinstance(value, int) and not isinstance(value, bool)


def validate_risk_object(risk) -> tuple[bool, str | None]:
	"""Validate a v2 `risk` object's shape. Pure; returns (ok, error_code|None).

	Hard failures are STRUCTURAL (wrong type, out-of-range integer) and return a stable
	snake_case error_code — but they are NEVER a reason to reject the snapshot; the caller
	warns-and-stores. Soft issues (unknown band string, unknown signal name) are NOT hard
	failures — see `risk_warnings`. `value` is heterogeneous (str | int | float | None,
	bool tolerated as an int) and is NEVER type-coerced.
	"""
	if not isinstance(risk, dict):
		return False, "risk_not_object"

	score = risk.get("score")
	if not _is_int(score) or not (0 <= score <= 100):
		return False, "risk_score_range"

	scorer_version = risk.get("scorer_version")
	if not _is_int(scorer_version) or scorer_version < 1:
		return False, "risk_scorer_version"

	# band must be a string, but an unknown band value is warn-only (not rejected).
	if not isinstance(risk.get("band"), str):
		return False, "risk_band_type"

	if _parse_snapshot_at(risk.get("computed_at")) is None:
		return False, "risk_computed_at"

	breakdown = risk.get("breakdown")
	if not isinstance(breakdown, list):
		return False, "risk_breakdown_not_list"

	for row in breakdown:
		if not isinstance(row, dict):
			return False, "risk_breakdown_row_not_object"
		if not isinstance(row.get("signal"), str):
			return False, "risk_signal_type"
		value = row.get("value")
		if not (value is None or isinstance(value, (str, int, float))):
			return False, "risk_value_type"
		weight = row.get("weight")
		if not _is_int(weight) or weight < 0:
			return False, "risk_weight"
		contribution = row.get("contribution")
		if not _is_int(contribution) or contribution < 0 or contribution > weight:
			return False, "risk_contribution_range"
		if not isinstance(row.get("reason"), str):
			return False, "risk_reason_type"

	return True, None


def risk_warnings(risk) -> list[str]:
	"""Soft, non-rejecting warnings for a risk object.

	Returns stable codes / band labels / signal NAMES only — NEVER transaction values
	(PII discipline). Safe to call on a structurally invalid object (guards each access).
	"""
	warnings: list[str] = []
	if not isinstance(risk, dict):
		return warnings
	band = risk.get("band")
	if isinstance(band, str) and band not in ("PASS", "REVIEW"):
		warnings.append(f"unknown_band:{band}")
	breakdown = risk.get("breakdown")
	if isinstance(breakdown, list):
		for row in breakdown:
			if isinstance(row, dict):
				signal = row.get("signal")
				if isinstance(signal, str) and signal not in _KNOWN_RISK_SIGNALS:
					warnings.append(f"unknown_signal:{signal}")
	return warnings


def _collect_risk_warnings(recent: list) -> list[str]:
	"""Walk recent[], validating any item that carries a `risk` object (field-presence
	keyed, per item). Returns the de-duplicated, sorted list of warning/error codes —
	signal names and stable codes only, never values."""
	codes: list[str] = []
	for item in recent:
		if isinstance(item, dict) and "risk" in item:
			ok_risk, err_code = validate_risk_object(item["risk"])
			if not ok_risk and err_code:
				codes.append(err_code)
			codes.extend(risk_warnings(item["risk"]))
	return sorted(set(codes))


def _coerce_int(value):
	"""Store an Int field defensively — non-int (e.g. a malformed string score) → None,
	so a degraded risk object never blocks the review-queue upsert."""
	return value if isinstance(value, int) and not isinstance(value, bool) else None


def _naive_dt(value):
	"""Parse an RFC-3339 timestamp to a NAIVE datetime for a typed Datetime column.

	`_parse_snapshot_at` yields a tz-aware datetime (`+00:00`), which MariaDB rejects for a
	real DATETIME column (the Single mirror doctypes dodge this because Singles store every
	field as text). We strip the tz, keeping the UTC wall-clock — these are Koya reference
	timestamps shown for display only and are labelled "(Koya)".
	"""
	dt = _parse_snapshot_at(value)
	if dt is not None and getattr(dt, "tzinfo", None) is not None:
		dt = dt.replace(tzinfo=None)
	return dt


def _reconcile_review_items(recent: list, received_at) -> None:
	"""Snapshot reconciliation for the review queue (G2): rebuild it from this push.

	Order: upsert every item with state == MANUAL_REVIEW AND a `risk` object (keyed by
	ref); then delete every existing review item whose ref is not in that set. The
	snapshot is authoritative for "what is currently pending review" — delete-immediately,
	never accumulate. Best-effort: a per-item failure is logged (ref only) and skipped so
	reconciliation can NEVER fail the mirror receive (the snapshot is already stored).
	"""
	current_refs = set()
	for item in recent:
		if not (isinstance(item, dict) and item.get("state") == "MANUAL_REVIEW" and "risk" in item):
			continue
		ref = item.get("ref")
		if not ref:
			continue
		current_refs.add(ref)
		try:
			risk = item.get("risk") if isinstance(item.get("risk"), dict) else {}
			if frappe.db.exists(_REVIEW_ITEM, ref):
				doc = frappe.get_doc(_REVIEW_ITEM, ref)
			else:
				doc = frappe.new_doc(_REVIEW_ITEM)
				doc.ref = ref
			doc.state = item.get("state")
			# hold_reason (Phase 4): additive field on the mirror item. Captured forward-compat —
			# absent -> None, never blocks the upsert. The exact Koya field name is pending the
			# settlement-decision endpoint sign-off (see step-05); `hold_reason` is the expected key.
			doc.hold_reason = item.get("hold_reason")
			doc.asset = item.get("asset")
			doc.kes_amount = item.get("kes_amount")
			doc.asset_amount = item.get("asset_amount")
			doc.created_at = _naive_dt(item.get("created_at"))
			doc.updated_at = _naive_dt(item.get("updated_at"))
			doc.risk_score = _coerce_int(risk.get("score"))
			doc.risk_band = risk.get("band") if isinstance(risk.get("band"), str) else None
			doc.scorer_version = _coerce_int(risk.get("scorer_version"))
			doc.risk_computed_at = _naive_dt(risk.get("computed_at"))
			doc.risk_breakdown_json = json.dumps(
				risk.get("breakdown") if isinstance(risk.get("breakdown"), list) else [],
				separators=(",", ":"),
			)
			doc.received_at = received_at
			doc.save(ignore_permissions=True)
		except Exception:
			get_logger().warning(f"review item upsert skipped ref={ref}")

	# Delete-missing: anything no longer in the current MANUAL_REVIEW+risk set.
	try:
		for name in frappe.get_all(_REVIEW_ITEM, pluck="name"):
			if name not in current_refs:
				frappe.delete_doc(_REVIEW_ITEM, name, ignore_permissions=True, force=True)
	except Exception:
		get_logger().warning("review item delete-missing sweep failed")


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

		# G3: audit (best-effort — never fails the receive).
		write_audit(
			"mirror_rates_received",
			correlation_id=koya_request_id,
			harness_request_id=correlation_id,
			detail={"rates_count": len(rates_list), "sources_count": len(sources)},
		)

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

		# v2 risk schema (Phase 3): validate any item carrying a `risk` object, keyed on
		# field presence per item — NEVER on schema_version. Warn-and-store: a malformed
		# risk object is logged (codes / signal names only, never values) and still stored.
		risk_warning_codes = _collect_risk_warnings(recent)
		if risk_warning_codes:
			get_logger().warning(
				f"mirror transactions risk validation warnings={risk_warning_codes} "
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

		# G2: rebuild the review queue from this snapshot (upsert MANUAL_REVIEW+risk items,
		# delete the rest). Best-effort inside the helper — never fails the receive.
		_reconcile_review_items(recent, doc.received_at)

		# G3: audit (best-effort — never fails the receive). Counts + key names only.
		manual_review_count = sum(
			1 for i in recent if isinstance(i, dict) and i.get("state") == "MANUAL_REVIEW"
		)
		risk_items_count = sum(1 for i in recent if isinstance(i, dict) and "risk" in i)
		write_audit(
			"mirror_transactions_received",
			correlation_id=koya_request_id,
			harness_request_id=correlation_id,
			detail={
				"recent_count": len(recent),
				"manual_review_count": manual_review_count,
				"risk_items_count": risk_items_count,
				"status_counts_keys": sorted((body.get("status_counts") or {}).keys()),
				"risk_warnings": len(risk_warning_codes),
			},
		)
		if risk_warning_codes:
			write_audit(
				"mirror_risk_validation_warning",
				correlation_id=koya_request_id,
				harness_request_id=correlation_id,
				outcome="warning",
				detail={"warning_count": len(risk_warning_codes), "codes": risk_warning_codes},
				error_code=risk_warning_codes[0],
			)

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

"""Phase-4 settlement decision — the harness half of reviewer approve/reject.

THE MONEY-MOVING DIRECTION. A compliance reviewer in the Phase-3 review queue approves or
rejects a held conversion; this module signs that decision with the inbound HMAC secret
(reusing `client.post_signed` — never a hand-rolled signer) and POSTs it to Koya's
settlement-decision endpoint. Koya validates against ITS OWN locked record and derives the
amount / destination itself — so the body is a decision keyed to a `session_ref` and carries
NOTHING about money: no amount, no destination, no asset, no payout instruction. That
absence is the injection-defense property (contract §4.4); do not add those fields "to be
safe" — Koya ignores them by design.

Three independent things must ALL hold before a real decision leaves the box:
  1. `harness_phase4_live_fire` is True in site_config (default / absent = False).
  2. The caller passes the server-side decision-role gate (compliance or System Manager).
  3. (Operational) Koya's endpoint is deployed and we are in a coordinated window.
With the flag OFF (the shipped default), the full validate -> send -> handle -> audit path
runs against a SIMULATED Koya response, so the UI + audit are exercised end-to-end without a
real decision leaving the box.
"""

import datetime
import uuid

import frappe

from harness.koya_harness import decision_render
from harness.koya_harness.audit import write_audit
from harness.koya_harness.client import post_signed
from harness.koya_harness.log import get_logger

_DECISION_PATH = "/internal/harness/settlement-decision"
_DECISION_ROLES = {"koya_harness_compliance", "System Manager"}
_REVIEW_ITEM = "Koya Review Item"
_LIVE_FIRE_KEY = "harness_phase4_live_fire"
_VALID_DECISIONS = {"APPROVE", "REJECT"}


# --------------------------------------------------------------------------- G1: the gate


def can_send_decisions() -> bool:
	"""Whether the current user holds a decision role (the membership the G1 gate enforces).
	A UI hint for defence-in-depth — the REAL gate is `_require_decision_role` on the send
	method, so this is only used to decide whether to draw the approve/reject affordance."""
	return bool(_DECISION_ROLES & set(frappe.get_roles()))


def _require_decision_role() -> None:
	"""G1 — the server-side money-path action gate. Independent of the Phase-3 READ gate
	(`review.py` `has_permission(... "read")`): that gates VIEWING the queue, this gates
	SENDING a decision. Both must hold. Raises before any body is built or sent."""
	if not can_send_decisions():
		raise frappe.PermissionError("Not permitted to send settlement decisions.")


# --------------------------------------------------------------------------- helpers


def _rfc3339_now() -> str:
	"""RFC 3339 ms UTC (Z) — matches the contract timestamp format (cf. health.py)."""
	now = datetime.datetime.now(datetime.timezone.utc)
	return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _live_fire_enabled() -> bool:
	"""The build ships with this OFF (flag absent). Flipping it ON is a coordinated
	joint-test action, never a routine config change."""
	return bool(frappe.conf.get(_LIVE_FIRE_KEY, False))


def _structural_error(message: str) -> dict:
	"""A client-side validation failure — the decision was never built or sent."""
	return {
		"ok": False,
		"kind": "invalid",
		"severity": "error",
		"message": message,
		"resulting_state": None,
		"resulting_label": None,
		"idempotent": None,
		"error_code": "validation_error",
		"sent": False,
	}


def _audit(event_type: str, **kwargs) -> None:
	"""Money-path audit wrapper. `write_audit` is already best-effort (it swallows + warns),
	but this is a MONEY action, so any surprise failure is logged PROMINENTLY here and still
	swallowed — an audit problem must NEVER break a decision send."""
	try:
		write_audit(event_type, **kwargs)
	except Exception:
		get_logger().error(
			f"MONEY-PATH audit write failed event={event_type} cid={kwargs.get('correlation_id')}"
		)


def _lookup_hold_reason(session_ref):
	"""The hold_reason carried on the review item (G4 field). Best-effort and forward-compat:
	tolerant of the item being gone or the column being absent — never fails the decision."""
	try:
		return frappe.db.get_value(_REVIEW_ITEM, session_ref, "hold_reason")
	except Exception:
		return None


# --------------------------------------------------------------------------- G3: response


def _handle_response(body, http_status) -> dict:
	"""G3: map a Koya response (or the transport envelope) to a UI reflection dict. Renders
	`resulting_state` as a STRING (never a hardcoded enum); idempotent- and conflict-safe;
	a transport failure is NEVER reported as landed."""
	body = body if isinstance(body, dict) else {}
	err = body.get("error") or {}
	err_code = err.get("code")

	# Transport-level failure (no HTTP response) — never claim it landed.
	if http_status is None or err_code == "transport_error":
		return {
			"ok": False,
			"kind": "transport_error",
			"severity": "warning",
			"resulting_state": None,
			"resulting_label": None,
			"idempotent": None,
			"error_code": err_code or "transport_error",
			"message": "The decision may not have landed — check the conversion state and retry.",
		}

	if http_status == 200 and body.get("ok"):
		data = body.get("data") or {}
		state = data.get("resulting_state")
		idempotent = bool(data.get("idempotent"))
		label = decision_render.resulting_state_label(state)
		return {
			"ok": True,
			"kind": "idempotent" if idempotent else "accepted",
			"severity": "info",
			"resulting_state": state,
			"resulting_label": label,
			"idempotent": idempotent,
			"error_code": None,
			"message": ("This decision was already processed — no change." if idempotent else label),
		}

	if http_status == 409:
		# Not in a decidable state (already resolved / auto-moved). Show the ACTUAL current
		# state if Koya included one; this is NOT a hard error.
		data = body.get("data") or {}
		current = data.get("resulting_state") or data.get("current_state")
		return {
			"ok": False,
			"kind": "conflict",
			"severity": "warning",
			"resulting_state": current,
			"resulting_label": (
				decision_render.resulting_state_label(current) if current else "No longer pending review."
			),
			"idempotent": None,
			"error_code": err_code or "conflict",
			"message": (
				f"This conversion is no longer pending review (current state: {current})."
				if current
				else "This conversion is no longer pending review."
			),
		}

	# 404 / 400 / 401 / 403 / 5xx — surface honestly.
	messages = {
		404: "Conversion not found at Koya.",
		400: "Koya rejected the request as malformed.",
		401: "Signature / replay / freshness rejected — a real channel problem.",
		403: "Forbidden — IP allowlist or permission rejected at Koya.",
	}
	base = messages.get(http_status, f"Koya returned HTTP {http_status}.")
	detail = f" ({err.get('message')})" if err.get("message") else ""
	if http_status == 401:
		get_logger().error("settlement decision rejected 401 — HMAC/replay/freshness channel problem")
	return {
		"ok": False,
		"kind": "error",
		"severity": "error",
		"resulting_state": None,
		"resulting_label": None,
		"idempotent": None,
		"error_code": err_code or f"http_{http_status}",
		"message": base + detail,
	}


def _simulated_response(decision: str):
	"""Live-fire OFF: a stand-in shaped EXACTLY like a real Koya 200-accepted response, so
	the G3 handler + G5 audit run end-to-end without a real decision leaving the box. The
	resulting_state mirrors the common pre-payment outcome for the decision."""
	state = "PAYMENT_PENDING" if decision == "APPROVE" else "REJECTED"
	body = {
		"ok": True,
		"data": {"resulting_state": state, "idempotent": False, "simulated": True},
	}
	return body, 200


# --------------------------------------------------------------------------- G2: send


@frappe.whitelist()
def send_settlement_decision(session_ref: str, decision: str, reason: str = None) -> dict:
	"""Sign and send (or, with live-fire OFF, simulate) a settlement decision for a held
	conversion. Returns a UI reflection dict (the G3 shape). Money-path: gated first,
	audited, body-minimal (no amount / destination / asset, ever)."""
	_require_decision_role()  # G1 — FIRST line, before any body is built or sent.

	# ---- validate: never send an invalid decision -------------------------------------
	decision = (decision or "").strip().upper()
	if decision not in _VALID_DECISIONS:
		return _structural_error("Decision must be APPROVE or REJECT.")
	if not session_ref:
		return _structural_error("A session_ref is required.")
	reason = (reason or "").strip()
	if decision == "REJECT" and not reason:
		return _structural_error("A reason is required to reject.")

	# ---- build the STABLE body — contract-exact, NOTHING about money ------------------
	request_id = str(uuid.uuid4()).lower()
	body = {
		"request_id": request_id,
		"session_ref": session_ref,
		"decision": decision,
		"reviewer": frappe.session.user,  # audit only — Koya does NOT trust this for authz
		"decided_at": _rfc3339_now(),
	}
	if reason:
		body["reason"] = reason

	hold_reason = _lookup_hold_reason(session_ref)

	# ---- audit the SEND: decision metadata ONLY (no amounts, no PII) ------------------
	# `reason` is reviewer-authored free text -> store presence/length, never the body, to
	# keep the audit log value-free like the rest of it.
	_audit(
		"settlement_decision_sent",
		correlation_id=session_ref,
		harness_request_id=request_id,
		detail={
			"decision": decision,
			"reviewer": frappe.session.user,
			"reason_present": bool(reason),
			"reason_len": len(reason),
			"hold_reason": hold_reason,
			"live_fire": _live_fire_enabled(),
		},
	)

	# ---- send (live-fire) or simulate (default OFF) -----------------------------------
	if _live_fire_enabled():
		resp_body, http_status = post_signed(_DECISION_PATH, body, with_status=True)
	else:
		resp_body, http_status = _simulated_response(decision)

	reflection = _handle_response(resp_body, http_status)
	reflection["request_id"] = request_id
	reflection["session_ref"] = session_ref
	reflection["live_fire"] = _live_fire_enabled()

	# ---- audit the RESPONSE -----------------------------------------------------------
	if reflection.get("ok"):
		outcome = "success"
	elif reflection.get("severity") == "warning":
		outcome = "warning"
	else:
		outcome = "failure"
	_audit(
		"settlement_decision_response",
		correlation_id=session_ref,
		harness_request_id=request_id,
		outcome=outcome,
		error_code=reflection.get("error_code"),
		detail={
			"resulting_state": reflection.get("resulting_state"),
			"idempotent": reflection.get("idempotent"),
			"kind": reflection.get("kind"),
		},
	)

	return reflection

"""Pure rendering / labeling helpers for Phase-4 settlement decisions.

NO `frappe` import — deterministic, DB-free, unit-testable in isolation (mirrors
`risk_render.py`). Forward-compat is the governing rule: an unknown `resulting_state` or an
unknown `hold_reason` must RENDER generically, never raise. The page JS renders the strings
these helpers produce, so the (hold_reason x decision) confirmation matrix and the
resulting_state UX mapping live in ONE place and stay Python-unit-testable (no JS<->Python
drift). Every public function is total — it returns a string for any input.
"""

# The five resulting_state strings Koya may return (frozen Phase-4 contract). Anything else
# renders generically — never hardcode an enum that would fail on a sixth.
_APPROVE_STATES = frozenset(
	{
		"PAYMENT_PENDING",  # risk-hold APPROVE — resumes pre-payment
		"PAYOUT_DETAILS_PENDING",  # compliance-hold APPROVE
		"DELIVERY_PENDING",  # delivery-hold APPROVE — retry BTC delivery (money is in)
	}
)

# The three hold-reason values (additive in the mirror payload; render-the-string). The
# post-payment case is materially different — money has already been collected.
_PREPAY_REASONS = frozenset({"risk_review_required", "compliance_review_required"})
_POSTPAY_REASON = "btc_delivery_retry_exhausted"


def resulting_state_label(state) -> str:
	"""G3.2 UX mapping. REFUND_PENDING MUST read differently from REJECTED — money is owed.
	Unknown state -> generic, never crash (forward-compat for a future sixth state)."""
	if state in _APPROVE_STATES:
		return f"Approved — conversion resuming ({state})"
	if state == "REJECTED":
		return "Rejected — declined, no funds were collected"
	if state == "REFUND_PENDING":
		return "Rejected — REFUND OWED to customer (booked for refund)"
	if state is None or state == "":
		return "Resulting state: —"
	return f"Resulting state: {state}"


def hold_reason_label(reason) -> str:
	"""G4.1 banner copy. No reason -> empty string (no banner). Unknown -> generic."""
	if reason == "risk_review_required":
		return "Held: risk review (pre-payment)"
	if reason == "compliance_review_required":
		return "Held: compliance review (pre-payment)"
	if reason == _POSTPAY_REASON:
		return "Held: BTC delivery failed after retries (PAYMENT RECEIVED)"
	if reason is None or reason == "":
		return ""
	return f"Held: {reason}"


def hold_reason_class(reason) -> str:
	"""CSS modifier for the hold-reason banner. The post-payment (money-in) case is styled
	distinctly so a reviewer cannot mistake it for a pre-payment hold."""
	if reason == _POSTPAY_REASON:
		return "postpay"
	if reason in _PREPAY_REASONS:
		return "prepay"
	if reason is None or reason == "":
		return "none"
	return "other"


def confirmation_text(hold_reason, decision) -> str:
	"""G4.2 reason-aware confirmation — the money-safety UX. A reviewer must NOT be able to
	reject a post-payment hold thinking it is a clean decline; the post-payment REJECT copy
	is the heaviest because it commits the company to a refund. Total: never raises."""
	dec = (decision or "").strip().upper()
	post_payment = hold_reason == _POSTPAY_REASON
	if dec == "APPROVE":
		if post_payment:
			return (
				"Approve and RETRY BTC delivery? KES has already been collected; "
				"this will attempt delivery again."
			)
		return "Approve and resume this conversion?"
	if dec == "REJECT":
		if post_payment:
			return "Reject? This will book a REFUND OBLIGATION — the customer's KES is owed back."
		return "Reject and decline this conversion? No funds were collected."
	return f"Confirm {decision} for this conversion?"


def no_risk_note(hold_reason) -> str:
	"""Detail-view copy for a hold with NO risk object, so a reviewer isn't confused by the
	absence of a score. Compliance & delivery holds are held by their own screens, not the risk
	scorer. Total: never raises."""
	if hold_reason == "compliance_review_required":
		return "Held by the compliance screen — not risk-scored (no risk score)."
	if hold_reason == _POSTPAY_REASON:
		return "Held after BTC delivery retries were exhausted — PAYMENT RECEIVED; not risk-scored."
	if hold_reason == "risk_review_required":
		# A risk hold normally carries a risk object; reaching here means it didn't.
		return "Flagged for risk review, but no risk score was provided."
	return "Held — not risk-scored."

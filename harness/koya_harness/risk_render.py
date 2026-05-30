"""Pure rendering / formatting helpers for v2 risk objects (Phase 3 review queue).

NO `frappe` import — these are deterministic, DB-free, and unit-testable in isolation.
Forward-compat is the governing rule: unknown bands, unknown signal names, and
unexpected value types must RENDER, never raise. The seven known v1 signals get friendly
value formatting (money / count / boolean-ish); anything else renders its raw value
verbatim. Every public function is total — it returns a string (or a safe default) for
any input rather than throwing.
"""

import html

# The seven known v1 signals (open-ish enum — unknown names render generically).
KNOWN_SIGNALS = (
	"amount_vs_kyc_tier",
	"velocity_count_24h",
	"velocity_volume_24h",
	"first_transaction",
	"destination_reuse_unknown",
	"structuring_pattern",
	"session_anomaly",
)

_MONEY_SIGNALS = frozenset({"amount_vs_kyc_tier", "velocity_volume_24h"})
_COUNT_SIGNALS = frozenset({"velocity_count_24h", "destination_reuse_unknown", "structuring_pattern"})
_BOOLEAN_SIGNALS = frozenset({"first_transaction", "session_anomaly"})


def _raw(value) -> str:
	"""Verbatim string for any value; None → em dash. Never raises."""
	if value is None:
		return "—"
	return str(value)


def format_kes(value) -> str:
	"""Format a numeric-ish value as 'KES 95,000'. Falls back to the raw value for
	anything that isn't a clean number — never raises."""
	if isinstance(value, bool) or value is None:
		return _raw(value)
	try:
		num = float(value)
	except TypeError, ValueError:
		return _raw(value)
	if num == int(num):
		return f"KES {int(num):,}"
	return f"KES {num:,.2f}"


def _count(value) -> str:
	"""Plain integer-with-separators for count signals; raw fallback."""
	if isinstance(value, bool) or value is None:
		return _raw(value)
	try:
		num = float(value)
	except TypeError, ValueError:
		return _raw(value)
	if num == int(num):
		return f"{int(num):,}"
	return f"{num:,}"


def _yes_no(value) -> str:
	"""Boolean-ish rendering for first_transaction / session_anomaly. Unknown string →
	verbatim."""
	if value is None:
		return "—"
	if isinstance(value, bool):
		return "Yes" if value else "No"
	if isinstance(value, (int, float)):
		return "Yes" if value else "No"
	s = str(value).strip().lower()
	if s in ("true", "yes", "y", "t", "1"):
		return "Yes"
	if s in ("false", "no", "n", "f", "0", ""):
		return "No"
	return str(value)


def value_for_signal(signal, value) -> str:
	"""Per-signal friendly value rendering. Unknown signal name or unexpected value type
	→ the raw value verbatim. Total: never raises for any (signal, value)."""
	try:
		if signal in _MONEY_SIGNALS:
			return format_kes(value)
		if signal in _COUNT_SIGNALS:
			return _count(value)
		if signal in _BOOLEAN_SIGNALS:
			return _yes_no(value)
		return _raw(value)
	except Exception:
		return _raw(value)


def band_class(band) -> str:
	"""CSS modifier suffix for a band badge. REVIEW = amber (matches the stale badge),
	PASS = neutral, anything else (incl. a future FAIL) = neutral with the band shown."""
	if band == "REVIEW":
		return "review"
	if band == "PASS":
		return "pass"
	return "other"


def _contribution_key(row) -> float:
	"""Sort/selection key — malformed or missing contribution sorts lowest."""
	if not isinstance(row, dict):
		return -1.0
	c = row.get("contribution")
	if isinstance(c, bool) or not isinstance(c, (int, float)):
		return -1.0
	return float(c)


def top_signal(breakdown):
	"""The breakdown row with the highest contribution, or None for empty/invalid input.
	Stable: ties keep the earliest row."""
	if not isinstance(breakdown, list):
		return None
	best = None
	best_key = None
	for row in breakdown:
		if not isinstance(row, dict):
			continue
		k = _contribution_key(row)
		if best is None or k > best_key:
			best = row
			best_key = k
	return best


def sort_breakdown(breakdown):
	"""Breakdown rows sorted by contribution desc. Zero-contribution rows are RETAINED
	(never filtered). Non-dict rows are dropped. Stable for ties (Python sort)."""
	if not isinstance(breakdown, list):
		return []
	rows = [r for r in breakdown if isinstance(r, dict)]
	return sorted(rows, key=_contribution_key, reverse=True)


def render_breakdown_html(breakdown) -> str:
	"""Render the full breakdown[] as an HTML <table> string. ALWAYS non-empty: an
	empty/invalid breakdown yields a single placeholder row. Zero-contribution rows are
	retained and marked muted (de-emphasized, not hidden). Unknown signals render
	verbatim. Every cell is HTML-escaped."""
	rows = sort_breakdown(breakdown)
	body = []
	for r in rows:
		signal = r.get("signal")
		signal_txt = html.escape(str(signal)) if signal is not None else "—"
		value_txt = html.escape(value_for_signal(signal, r.get("value")))
		weight = r.get("weight")
		contribution = r.get("contribution")
		reason = r.get("reason")
		weight_txt = html.escape(_raw(weight))
		contrib_txt = html.escape(_raw(contribution))
		reason_txt = html.escape(str(reason)) if reason is not None else ""
		muted = ""
		if (
			isinstance(contribution, (int, float))
			and not isinstance(contribution, bool)
			and contribution == 0
		):
			muted = " krq-bd-row--muted"
		body.append(
			f'<tr class="krq-bd-row{muted}">'
			f'<td class="krq-signal">{signal_txt}</td>'
			f"<td>{value_txt}</td>"
			f'<td class="krq-num">{weight_txt}</td>'
			f'<td class="krq-num">{contrib_txt}</td>'
			f'<td class="krq-reason">{reason_txt}</td>'
			f"</tr>"
		)
	if not body:
		body.append('<tr><td colspan="5" class="krq-empty">No breakdown signals.</td></tr>')
	head = (
		'<table class="krq-bd-table"><thead><tr>'
		"<th>Signal</th><th>Value</th>"
		'<th class="krq-num">Weight</th><th class="krq-num">Contribution</th>'
		"<th>Reason</th>"
		"</tr></thead><tbody>"
	)
	return head + "".join(body) + "</tbody></table>"

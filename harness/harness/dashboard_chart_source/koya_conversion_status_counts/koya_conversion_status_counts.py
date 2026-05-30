"""Dashboard Chart Source — conversion status distribution from the latest mirror snapshot.

`Koya Transaction Mirror` stores `status_counts` as JSON inside a Single doctype, which a
standard aggregate Dashboard Chart cannot read. This source parses that JSON and returns the
frappe-charts shape (`{labels, datasets}`) so a `chart_type: Custom` chart can render the live
conversion-state distribution on the DESK. (This reuses the CRM *concept* of a method computing
chart data — HARNESS-RECON-CRM Q3 — wired through Frappe core's chart source, not an SPA.)

Discipline carried from the rest of the app:
- Forward-compat / total: a missing Single, blank value, invalid JSON, or non-dict yields an
  EMPTY chart — never raises.
- Renders the LATEST snapshot only. The authoritative staleness signal stays the mirror-status
  page's stale badge (Phase 2/3); this does not duplicate stale logic.
- Zero-count states are omitted for legibility (a flat 15-state dict is mostly zeros) — a
  presentation choice, not a data filter; the raw counts live on the mirror doctype.
"""

import json

import frappe
from frappe.utils.dashboard import cache_source

_MIRROR = "Koya Transaction Mirror"


@frappe.whitelist()
@cache_source
def get(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
):
	"""Entry point the desk dashboard calls for the Custom chart. Delegates to `_chart()` so
	the data logic stays unit-testable without the cache/whitelist wrappers."""
	return _chart()


def _chart() -> dict:
	counts = _status_counts()
	# Non-zero states only, highest first — a legible bar chart of where conversions sit now.
	items = [
		(k, v) for k, v in counts.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and v
	]
	items.sort(key=lambda kv: kv[1], reverse=True)
	return {
		"labels": [k for k, _ in items],
		"datasets": [{"name": "Conversions", "values": [v for _, v in items]}],
	}


def _status_counts() -> dict:
	"""The status_counts dict from the latest Transaction Mirror snapshot. Total: any problem
	(missing Single, null/blank, invalid JSON, non-dict) yields {}."""
	try:
		raw = frappe.db.get_single_value(_MIRROR, "status_counts_json")
		if not raw:
			return {}
		data = json.loads(raw)
		return data if isinstance(data, dict) else {}
	except Exception:
		return {}

"""Keep kronos.koyabank.com out of every search index / crawler.

kronos is an INTERNAL control-plane app — it must never be indexed or crawled. Two signals,
both code-side so they can't be reverted from the UI:

1. `set_no_index_headers` (an `after_request` hook): stamps `X-Robots-Tag: noindex,...` on
   EVERY response of the site (it runs for all installed apps' routes — desk, web, api). This
   is the authoritative de-index signal: search engines honour it even for already-indexed
   URLs once they re-crawl, and it does not depend on a crawler parsing HTML (works on every
   content type). Best-effort: it can never break a response.

2. `enforce_robots_txt` (an `after_migrate` hook): keeps /robots.txt as Disallow-all
   (Website Settings.robots_txt — the source `frappe/www/robots.py` renders), re-applied on
   every migrate so it survives.

NOTE (operational, not code): the durable fix for an internal app is that it should not be
internet-reachable / should sit behind auth + an IP allowlist at the edge. These signals stop
indexing; they do not replace network controls. For URLs ALREADY in an index, a Search Console
"Removals" request speeds removal — the noindex header makes it permanent on re-crawl.
"""

import frappe

# noindex (drop from index) + nofollow (don't follow links) + noarchive (no cached copy) +
# nosnippet (no snippet) + noimageindex (don't index images).
_X_ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex"
_ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


def set_no_index_headers(response=None, request=None, **kwargs):
	"""after_request hook — site-wide X-Robots-Tag: noindex on every response."""
	try:
		if response is not None and hasattr(response, "headers"):
			response.headers["X-Robots-Tag"] = _X_ROBOTS
	except Exception:
		# Never let an indexing header break a response.
		pass


def enforce_robots_txt():
	"""after_migrate hook — pin /robots.txt to Disallow-all (code-enforced)."""
	try:
		if frappe.db.get_single_value("Website Settings", "robots_txt") != _ROBOTS_TXT:
			frappe.db.set_single_value("Website Settings", "robots_txt", _ROBOTS_TXT)
	except Exception:
		frappe.logger().warning("noindex: could not enforce robots_txt")

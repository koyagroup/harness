import frappe

from harness.koya_harness.client import post_signed


@frappe.whitelist()
def test_connection(echo: str = "hello") -> dict:
	"""Send a signed ping to Koya. Returns the response envelope."""
	return post_signed("/internal/harness/ping", {"echo": echo})

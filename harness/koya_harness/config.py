import frappe

_SECRET_KEY = "harness_inbound_secret"
_BASE_URL_KEY = "harness_koya_base_url"


def get_inbound_secret() -> str:
	secret = frappe.conf.get(_SECRET_KEY)
	if not secret:
		frappe.throw("Harness inbound secret is not configured")
	return secret


def get_koya_base_url() -> str:
	url = frappe.conf.get(_BASE_URL_KEY)
	if not url:
		frappe.throw("Koya base URL is not configured")
	return url.rstrip("/")

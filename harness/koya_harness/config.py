import frappe

_SECRET_KEY = "harness_inbound_secret"
_OUTBOUND_SECRET_KEY = "harness_outbound_secret"
_BASE_URL_KEY = "harness_koya_base_url"


def get_inbound_secret() -> str:
	secret = frappe.conf.get(_SECRET_KEY)
	if not secret:
		frappe.throw("Harness inbound secret is not configured")
	return secret


def get_outbound_secret() -> str:
	"""Secret for verifying inbound Koya→harness display-mirror pushes (Phase 2).

	Read at request time (never cached at module load) so a rotated value picked
	up by the web tier first is used immediately. Distinct from the inbound
	(H→K signing) secret so a leak of one direction can't forge the other.
	"""
	secret = frappe.conf.get(_OUTBOUND_SECRET_KEY)
	if not secret:
		frappe.throw(f"Harness outbound secret ({_OUTBOUND_SECRET_KEY}) is not configured")
	return secret


def get_koya_base_url() -> str:
	url = frappe.conf.get(_BASE_URL_KEY)
	if not url:
		frappe.throw("Koya base URL is not configured")
	return url.rstrip("/")

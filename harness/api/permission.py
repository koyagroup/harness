"""App-launcher permission gate for the Koya Harness desk app.

`check_app_permission` decides whether the harness tile shows on the /apps launcher (and the
app switcher) for the current user. It mirrors Frappe CRM's `crm.api.check_app_permission`
pattern, but keyed on the harness's own roles. This is a VISIBILITY gate only — every
data-bearing endpoint/doctype enforces its own server-side permission (the read gates in
`koya_harness/api/review.py` and the doctype role perms); this just keeps the launcher tidy
for users with no harness business.

Not whitelisted: it is called server-side by the apps-screen resolver, not over HTTP.
"""

import frappe

_HARNESS_ROLES = {"System Manager", "koya_harness_compliance", "koya_harness_ops"}


def check_app_permission() -> bool:
	"""True if the current user should see the Koya Harness app tile."""
	if frappe.session.user == "Administrator":
		return True
	return bool(_HARNESS_ROLES & set(frappe.get_roles()))

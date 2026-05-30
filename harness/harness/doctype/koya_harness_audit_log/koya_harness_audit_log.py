"""Koya Harness Audit Log — append-only record of every mirror receive + future webhook
decision (Phase 4) and ledger post (Phase 8).

Write-only via code (`audit.write_audit`, `ignore_permissions=True`). No role may write,
edit, or delete through the UI: every field is read-only, no permission row grants
delete, and `on_trash` hard-blocks deletion as defence in depth. `detail_json` carries
key names + counts + outcomes ONLY — never PII, never transaction values.
"""

import frappe
from frappe.model.document import Document


class KoyaHarnessAuditLog(Document):
	def on_trash(self):
		# Append-only: not even a System Manager deletes audit rows through the framework.
		frappe.throw(frappe._("Koya Harness Audit Log is append-only and cannot be deleted."))

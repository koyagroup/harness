"""Koya Transaction Mirror — Single doctype holding the latest transaction summary
snapshot pushed by Koya.

READ-ONLY DISPLAY. Never read back as authoritative for any harness decision. Each
push OVERWRITES the snapshot (snapshot mode). `pii_warning` surfaces the defense-in-
depth PII guard (Wire Contract v1.1 §3.4) when a forbidden key slips through Koya-side.
"""

from frappe.model.document import Document


class KoyaTransactionMirror(Document):
	pass

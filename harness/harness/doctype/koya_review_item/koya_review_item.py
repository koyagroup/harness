"""Koya Review Item — a projection of one MANUAL_REVIEW conversion carrying a risk score.

Rows are upserted/deleted by the transactions mirror receiver per snapshot (snapshot
mode — the queue is rebuilt each push, never accumulated). The desk UI is read-only; all
writes happen in code with `ignore_permissions=True`. This is display/control-plane only:
nothing here is ever read back as authoritative for a money-path decision.
"""

from frappe.model.document import Document


class KoyaReviewItem(Document):
	pass

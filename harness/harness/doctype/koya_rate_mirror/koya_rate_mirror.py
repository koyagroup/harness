"""Koya Rate Mirror — Single doctype holding the latest rates snapshot pushed by Koya.

READ-ONLY DISPLAY. This data is never read back as authoritative for any harness
decision; it exists only to show staff what Koya is currently quoting. Each push
OVERWRITES the snapshot (snapshot mode — no history, no delta merging).
"""

from frappe.model.document import Document


class KoyaRateMirror(Document):
	pass

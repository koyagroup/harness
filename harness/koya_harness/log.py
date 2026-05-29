"""Shared logger for the Phase-2 mirror path.

Frappe's default logger level is ERROR, which would drop the receipt-correlation INFO
lines and the PII-guard WARNING. We pin this logger to INFO so cross-system correlation
(Koya request_id ↔ harness correlation id) and the §3.4 PII warning are actually recorded.
Never log secret material; key names only for the PII guard.
"""

import frappe


def get_logger():
	logger = frappe.logger("koya_harness")
	logger.setLevel("INFO")
	return logger

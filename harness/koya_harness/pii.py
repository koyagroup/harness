"""Defense-in-depth PII guard for the transactions mirror (Wire Contract v1.1 §3.4).

Koya is the contract enforcer — its transactions payload MUST NOT carry user-identifying
fields. This is the harness-side safety net: if a forbidden key ever appears (Koya's PII
enforcement regresses), we warn-and-STORE — never reject — because Koya remains the source
of truth and may have a legitimate reason. We log/surface the offending key *name* only,
never its value.
"""

_FORBIDDEN_KEYS = frozenset(
	{
		"email",
		"phone",
		"name",
		"user_id",
		"customer_id",
		"ip_address",
		"device_id",
		"device_fingerprint",
	}
)


def scan_recent_for_pii(recent: list) -> list[str]:
	"""Return the sorted set of forbidden key names found across `recent[]` items.

	Only key names are returned — never values — so the result is safe to log and
	display. An empty list means the payload is clean.
	"""
	found: set[str] = set()
	if not isinstance(recent, list):
		return []
	for item in recent:
		if isinstance(item, dict):
			found.update(_FORBIDDEN_KEYS.intersection(item.keys()))
	return sorted(found)

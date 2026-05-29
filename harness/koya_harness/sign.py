import hashlib
import hmac


def compute_signature(secret: str, ts: str, nonce: str, raw_body: bytes) -> str:
	"""HMAC-SHA256(secret, ts + "." + nonce + "." + raw_body) -> 64-char lowercase hex.

	`ts` and `nonce` are the ASCII strings as they appear on the wire.
	`raw_body` is the exact byte sequence of the HTTP body. Do not re-serialize.
	"""
	signing_string = ts.encode("ascii") + b"." + nonce.encode("ascii") + b"." + raw_body
	return hmac.new(
		secret.encode("utf-8"),
		signing_string,
		hashlib.sha256,
	).hexdigest()

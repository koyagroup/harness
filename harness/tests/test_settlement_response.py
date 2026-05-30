"""G3 — response handling (fire-with-confirmation).

Every Koya response class maps to a UI reflection that tells the reviewer the REAL outcome:
200-accepted reflects resulting_state; 200-idempotent says "already processed" (no double
submit, no error); 409 shows the actual current state, NOT a hard error; 4xx surface
honestly; a transport failure says "may not have landed" and NEVER claims success. The
resulting_state is rendered as a STRING — REFUND_PENDING must read differently from REJECTED,
and an unknown sixth state must render generically without crashing.
"""

import unittest

from harness.koya_harness import decision_render
from harness.koya_harness.api import settlement

_H = settlement._handle_response


def _ok(state, idempotent=False):
	return {"ok": True, "data": {"resulting_state": state, "idempotent": idempotent}}


class TestHandleResponse(unittest.TestCase):
	# ---- 200 accepted ----
	def test_200_accepted_reflects_state(self):
		r = _H(_ok("PAYMENT_PENDING"), 200)
		self.assertTrue(r["ok"])
		self.assertEqual(r["kind"], "accepted")
		self.assertEqual(r["resulting_state"], "PAYMENT_PENDING")
		self.assertIn("resuming", r["resulting_label"])
		self.assertFalse(r["idempotent"])

	# ---- 200 idempotent (double-click / retry) ----
	def test_200_idempotent_no_double_submit_no_error(self):
		r = _H(_ok("REJECTED", idempotent=True), 200)
		self.assertTrue(r["ok"])
		self.assertEqual(r["kind"], "idempotent")
		self.assertTrue(r["idempotent"])
		self.assertEqual(r["severity"], "info")  # not an error
		self.assertIn("already processed", r["message"].lower())

	# ---- 409 conflict ----
	def test_409_shows_current_state_not_hard_error(self):
		r = _H({"ok": False, "error": {"code": "conflict"}, "data": {"resulting_state": "COMPLETED"}}, 409)
		self.assertFalse(r["ok"])
		self.assertEqual(r["kind"], "conflict")
		self.assertEqual(r["severity"], "warning")  # NOT a hard error
		self.assertEqual(r["resulting_state"], "COMPLETED")

	def test_409_without_current_state(self):
		r = _H({"ok": False, "error": {"code": "conflict"}}, 409)
		self.assertEqual(r["kind"], "conflict")
		self.assertIn("no longer pending", r["message"].lower())

	# ---- 4xx surfaced honestly ----
	def test_404_surfaced(self):
		r = _H({"ok": False, "error": {"code": "not_found"}}, 404)
		self.assertEqual(r["severity"], "error")
		self.assertIn("not found", r["message"].lower())

	def test_400_surfaced(self):
		r = _H({"ok": False, "error": {"code": "validation_error", "message": "bad"}}, 400)
		self.assertEqual(r["severity"], "error")
		self.assertIn("malformed", r["message"].lower())

	def test_401_surfaced(self):
		r = _H({"ok": False, "error": {"code": "signature_mismatch"}}, 401)
		self.assertEqual(r["severity"], "error")
		self.assertEqual(r["error_code"], "signature_mismatch")

	def test_403_surfaced(self):
		r = _H({"ok": False, "error": {"code": "forbidden"}}, 403)
		self.assertEqual(r["severity"], "error")
		self.assertIn("forbidden", r["message"].lower())

	# ---- transport failure: never claim it landed ----
	def test_transport_error_status_none(self):
		r = _H({"ok": False, "error": {"code": "transport_error"}}, None)
		self.assertFalse(r["ok"])
		self.assertEqual(r["kind"], "transport_error")
		self.assertEqual(r["severity"], "warning")
		self.assertIn("may not have landed", r["message"].lower())
		self.assertIsNone(r["resulting_state"])

	def test_transport_error_code_even_with_status(self):
		r = _H({"ok": False, "error": {"code": "transport_error", "message": "HTTP 502"}}, 502)
		self.assertEqual(r["kind"], "transport_error")


class TestResultingStateLabel(unittest.TestCase):
	def test_three_approve_states(self):
		for s in ("PAYMENT_PENDING", "PAYOUT_DETAILS_PENDING", "DELIVERY_PENDING"):
			self.assertIn("Approved", decision_render.resulting_state_label(s))
			self.assertIn(s, decision_render.resulting_state_label(s))

	def test_rejected_vs_refund_read_differently(self):
		rejected = decision_render.resulting_state_label("REJECTED")
		refund = decision_render.resulting_state_label("REFUND_PENDING")
		self.assertNotEqual(rejected, refund)
		self.assertIn("no funds were collected", rejected.lower())
		self.assertIn("refund", refund.lower())
		self.assertIn("owed", refund.lower())

	def test_unknown_sixth_state_renders_generically(self):
		label = decision_render.resulting_state_label("SOME_NEW_STATE_V2")
		self.assertIn("SOME_NEW_STATE_V2", label)  # rendered, not crashed

	def test_none_state(self):
		self.assertIsInstance(decision_render.resulting_state_label(None), str)


if __name__ == "__main__":
	unittest.main()

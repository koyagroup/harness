"""HARNESS-AUDIT-VIEW — the decision-history read API over the append-only audit log.

Pairs settlement_decision_sent ↔ settlement_decision_response by harness_request_id into one
logical record per decision. Decision events only (system events excluded). Compliance / System
Manager gated. Value-free: surfaces only what the audit stored (no raw reason text / amount / PII).
Rows are written through the real `write_audit` and stay inside the test transaction.
"""

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness.api import audit_view
from harness.koya_harness.audit import write_audit

_AUDIT = "Koya Harness Audit Log"
_COMPLIANCE = "koya_harness_compliance"
_OPS = "koya_harness_ops"


class TestDecisionHistory(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(lambda: frappe.set_user("Administrator"))
		frappe.set_user("Administrator")  # System Manager → passes the gate
		frappe.db.delete(_AUDIT)

	def _sent(self, rid, session_ref, decision="APPROVE", hold_reason="risk_review_required", reason=""):
		write_audit(
			"settlement_decision_sent",
			correlation_id=session_ref,
			harness_request_id=rid,
			detail={
				"decision": decision,
				"reviewer": "reviewer@harness.test",
				"reason_present": bool(reason),
				"reason_len": len(reason),
				"hold_reason": hold_reason,
				"live_fire": False,
			},
		)

	def _response(
		self, rid, session_ref, resulting_state="PAYMENT_PENDING", outcome="success", error_code=None
	):
		write_audit(
			"settlement_decision_response",
			correlation_id=session_ref,
			harness_request_id=rid,
			outcome=outcome,
			error_code=error_code,
			detail={"resulting_state": resulting_state, "idempotent": False, "kind": "accepted"},
		)

	def _make_user(self, email, roles):
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		u = frappe.new_doc("User")
		u.email = email
		u.first_name = "Test"
		u.send_welcome_email = 0
		u.flags.no_welcome_mail = True
		u.insert(ignore_permissions=True)
		u.add_roles(*roles)
		return email

	# ---- pairing ----
	def test_sent_response_pair_one_record(self):
		self._sent("req-1", "KYA-1", decision="APPROVE", hold_reason="risk_review_required")
		self._response("req-1", "KYA-1", resulting_state="PAYMENT_PENDING")
		res = audit_view.decision_history()
		self.assertTrue(res["permitted"])
		self.assertEqual(res["count"], 1)
		rec = res["records"][0]
		self.assertEqual(rec["session_ref"], "KYA-1")
		self.assertEqual(rec["decision"], "APPROVE")
		self.assertEqual(rec["resulting_state"], "PAYMENT_PENDING")
		self.assertEqual(rec["outcome"], "success")
		self.assertEqual(rec["status"], "responded")
		self.assertEqual(rec["hold_reason_label"], "Held: risk review (pre-payment)")
		self.assertTrue(rec["decided_at"])
		self.assertTrue(rec["response_time"])

	def test_sent_without_response_is_pending(self):
		self._sent("req-2", "KYA-2")
		rec = audit_view.decision_history()["records"][0]
		self.assertEqual(rec["status"], "pending")
		self.assertIsNone(rec["resulting_state"])
		self.assertEqual(rec["resulting_label"], "")

	def test_multiple_attempts_same_session_paired_separately(self):
		# Two decision attempts on the same session_ref → two distinct records (paired by request id).
		self._sent("req-a", "KYA-3", decision="REJECT", reason="x")
		self._response("req-a", "KYA-3", resulting_state="REJECTED")
		self._sent("req-b", "KYA-3", decision="APPROVE")
		self._response("req-b", "KYA-3", resulting_state="PAYMENT_PENDING")
		res = audit_view.decision_history()
		self.assertEqual(res["count"], 2)
		self.assertEqual({r["decision"] for r in res["records"]}, {"APPROVE", "REJECT"})

	# ---- decision events only ----
	def test_system_events_excluded(self):
		self._sent("req-4", "KYA-4")
		self._response("req-4", "KYA-4")
		write_audit("mirror_transactions_received", correlation_id="koya-x", detail={"recent_count": 5})
		write_audit("health_ping_received", correlation_id="koya-y", detail={"echo_present": True})
		res = audit_view.decision_history()
		self.assertEqual(res["count"], 1)  # only the decision pair, not the 2 system events

	# ---- role gate ----
	def test_ops_user_not_permitted(self):
		self._sent("req-5", "KYA-5")
		frappe.set_user(self._make_user("av_ops@harness.test", [_OPS]))
		res = audit_view.decision_history()
		self.assertFalse(res["permitted"])
		self.assertEqual(res["records"], [])

	def test_compliance_user_sees_records(self):
		self._sent("req-6", "KYA-6")
		self._response("req-6", "KYA-6")
		frappe.set_user(self._make_user("av_comp@harness.test", [_COMPLIANCE]))
		res = audit_view.decision_history()
		self.assertTrue(res["permitted"])
		self.assertEqual(res["count"], 1)

	# ---- defensive parse ----
	def test_missing_detail_keys_no_crash(self):
		write_audit("settlement_decision_sent", correlation_id="KYA-7", harness_request_id="req-7", detail={})
		write_audit(
			"settlement_decision_response",
			correlation_id="KYA-7",
			harness_request_id="req-7",
			outcome="failure",
			error_code="not_found",
			detail={},
		)
		rec = audit_view.decision_history()["records"][0]
		self.assertIsNone(rec["decision"])  # missing key tolerated
		self.assertEqual(rec["error_code"], "not_found")
		self.assertEqual(rec["status"], "responded")

	# ---- value-free ----
	def test_output_carries_no_raw_reason_or_amount(self):
		self._sent("req-8", "KYA-8", reason="structuring near 95000")  # reason text NOT stored
		self._response("req-8", "KYA-8")
		blob = frappe.as_json(audit_view.decision_history())
		self.assertNotIn("structuring", blob)
		self.assertNotIn("95000", blob)

	# ---- filter ----
	def test_filter_by_decision(self):
		self._sent("req-9", "KYA-9", decision="APPROVE")
		self._response("req-9", "KYA-9")
		self._sent("req-10", "KYA-10", decision="REJECT", reason="x")
		self._response("req-10", "KYA-10", resulting_state="REJECTED")
		res = audit_view.decision_history(filters={"decision": "REJECT"})
		self.assertEqual(res["count"], 1)
		self.assertEqual(res["records"][0]["decision"], "REJECT")

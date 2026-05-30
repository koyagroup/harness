"""G1 — v2 risk-schema tolerance on the transactions mirror receiver.

The receiver must handle v1 (no `risk` field anywhere) and v2 (some recent[] items carry
`risk`) IDENTICALLY. It keys on field presence (`"risk" in item`) PER ITEM — never on
schema_version. Malformed risk objects are warn-and-store (logged with codes / signal
names only, never values) — the snapshot is always stored; Koya is the source of truth.

These tests exercise the whitelisted handler in-process with a faked signed request and a
mocked logger to assert the warn-and-store behaviour, plus direct unit tests of the pure
`validate_risk_object` / `risk_warnings` helpers (no DB).
"""

import json
import time
import uuid
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from harness.koya_harness import verify as V
from harness.koya_harness.api import mirrors
from harness.koya_harness.sign import compute_signature

TEST_SECRET = "TEST_DO_NOT_USE_IN_PRODUCTION_0123456789abcdef"
_TXN = "Koya Transaction Mirror"


class FakeReq:
	def __init__(self, headers: dict, body: bytes):
		self.headers = headers
		self._body = body

	def get_data(self) -> bytes:
		return self._body


def _signed_headers(raw):
	ts = str(int(time.time()))
	nonce = str(uuid.uuid4()).lower()
	return {
		"Content-Type": "application/json",
		"X-Harness-Timestamp": ts,
		"X-Harness-Nonce": nonce,
		"X-Harness-Signature": compute_signature(TEST_SECRET, ts, nonce, raw),
	}


def _valid_risk(score=78, band="REVIEW", signal="amount_vs_kyc_tier", value="95000"):
	return {
		"score": score,
		"band": band,
		"scorer_version": 1,
		"computed_at": "2026-06-01T10:14:33.000Z",
		"breakdown": [
			{
				"signal": signal,
				"value": value,
				"weight": 25,
				"contribution": 23,
				"reason": "KES 95,000 vs Tier-1 limit KES 100,000 (95%)",
			}
		],
	}


def _risk_multi_value():
	"""A risk object whose breakdown rows carry string, number, and null values."""
	risk = _valid_risk()
	risk["breakdown"] = [
		{"signal": "amount_vs_kyc_tier", "value": "95000", "weight": 25, "contribution": 23, "reason": "r"},
		{"signal": "velocity_count_24h", "value": 8, "weight": 15, "contribution": 5, "reason": "r"},
		{"signal": "first_transaction", "value": None, "weight": 10, "contribution": 0, "reason": "r"},
	]
	return risk


def _item(ref, state="MANUAL_REVIEW", risk=None):
	item = {
		"ref": ref,
		"state": state,
		"asset": "BTC",
		"created_at": "2026-06-01T10:00:00.000Z",
		"updated_at": "2026-06-01T10:14:00.000Z",
		"kes_amount": "95000.00",
		"asset_amount": "0.018",
	}
	if risk is not None:
		item["risk"] = risk
	return item


def _body(recent, schema_version=1):
	return {
		"request_id": str(uuid.uuid4()),
		"schema_version": schema_version,
		"snapshot_at": "2026-06-01T10:14:56.789Z",
		"status_counts": {"MANUAL_REVIEW": 1, "COMPLETED": 1},
		"recent": recent,
		"recent_count": len(recent),
	}


class TestV2SchemaReceiver(IntegrationTestCase):
	def setUp(self):
		frappe.local.response = frappe._dict()
		p1 = patch.object(V, "get_outbound_secret", return_value=TEST_SECRET)
		p2 = patch.object(frappe.db, "commit")  # keep writes inside the test transaction
		p1.start()
		p2.start()
		self.addCleanup(p1.stop)
		self.addCleanup(p2.stop)

	def _call(self, body: dict, logger=None):
		raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
		frappe.local.request = FakeReq(_signed_headers(raw), raw)
		frappe.local.response = frappe._dict()
		if logger is not None:
			with patch.object(mirrors, "get_logger", return_value=logger):
				return mirrors.transactions()
		return mirrors.transactions()

	def _stored_recent(self):
		return json.loads(frappe.db.get_single_value(_TXN, "recent_json"))

	# ---- v1 / v2 identical handling ---------------------------------------
	def test_v1_no_risk_stored_no_warning(self):
		ml = MagicMock()
		res = self._call(_body([_item("KYA-2026-06-01-0001", state="COMPLETED")]), logger=ml)
		self.assertTrue(res["ok"])
		self.assertEqual(self._stored_recent()[0]["ref"], "KYA-2026-06-01-0001")
		self.assertFalse(ml.warning.called)  # no PII, no risk → no warnings

	def test_v2_mixed_items_with_and_without_risk(self):
		ml = MagicMock()
		recent = [
			_item("KYA-2026-06-01-0002", state="MANUAL_REVIEW", risk=_valid_risk()),
			_item("KYA-2026-06-01-0003", state="COMPLETED"),  # no risk
		]
		res = self._call(_body(recent), logger=ml)
		self.assertTrue(res["ok"])
		stored = self._stored_recent()
		self.assertEqual(len(stored), 2)
		self.assertIn("risk", stored[0])
		self.assertNotIn("risk", stored[1])
		self.assertFalse(ml.warning.called)

	def test_v2_value_types_all_stored_no_warning(self):
		ml = MagicMock()
		res = self._call(_body([_item("KYA-2026-06-01-0004", risk=_risk_multi_value())]), logger=ml)
		self.assertTrue(res["ok"])
		stored_risk = self._stored_recent()[0]["risk"]
		values = [r["value"] for r in stored_risk["breakdown"]]
		self.assertEqual(values, ["95000", 8, None])  # stored verbatim, no coercion
		self.assertFalse(ml.warning.called)

	# ---- warn-and-store ---------------------------------------------------
	def test_v2_malformed_score_warns_and_stores(self):
		ml = MagicMock()
		res = self._call(_body([_item("KYA-2026-06-01-0005", risk=_valid_risk(score=150))]), logger=ml)
		self.assertTrue(res["ok"])  # stored, NOT rejected
		self.assertEqual(self._stored_recent()[0]["risk"]["score"], 150)  # verbatim
		texts = [c.args[0] for c in ml.warning.call_args_list]
		self.assertTrue(any("risk_score_range" in t for t in texts))
		self.assertFalse(any("150" in t for t in texts))  # the value never leaks into the log

	def test_v2_unknown_signal_warns_and_stores(self):
		ml = MagicMock()
		risk = _valid_risk(signal="exotic_new_signal")
		res = self._call(_body([_item("KYA-2026-06-01-0006", risk=risk)]), logger=ml)
		self.assertTrue(res["ok"])
		self.assertEqual(self._stored_recent()[0]["risk"]["breakdown"][0]["signal"], "exotic_new_signal")
		texts = [c.args[0] for c in ml.warning.call_args_list]
		self.assertTrue(any("unknown_signal:exotic_new_signal" in t for t in texts))

	# ---- schema_version is never a gate -----------------------------------
	def test_schema_version_1_with_risk_works(self):
		res = self._call(_body([_item("KYA-2026-06-01-0007", risk=_valid_risk())], schema_version=1))
		self.assertTrue(res["ok"])
		self.assertIn("risk", self._stored_recent()[0])

	def test_schema_version_99_future_works(self):
		res = self._call(_body([_item("KYA-2026-06-01-0008", risk=_valid_risk())], schema_version=99))
		self.assertTrue(res["ok"])
		self.assertEqual(frappe.db.get_single_value(_TXN, "schema_version"), 99)
		self.assertIn("risk", self._stored_recent()[0])


class TestValidateRiskObject(IntegrationTestCase):
	"""Direct unit tests of the pure validator/warning helpers (no request, no DB)."""

	def test_valid(self):
		self.assertEqual(mirrors.validate_risk_object(_valid_risk()), (True, None))

	def test_value_types_string_number_null(self):
		self.assertEqual(mirrors.validate_risk_object(_risk_multi_value()), (True, None))

	def test_not_object(self):
		self.assertEqual(mirrors.validate_risk_object("nope"), (False, "risk_not_object"))

	def test_score_out_of_range(self):
		self.assertEqual(mirrors.validate_risk_object(_valid_risk(score=101))[1], "risk_score_range")
		self.assertEqual(mirrors.validate_risk_object(_valid_risk(score=-1))[1], "risk_score_range")

	def test_score_bool_rejected(self):
		# bool is a subclass of int but is NOT a valid score.
		self.assertEqual(mirrors.validate_risk_object(_valid_risk(score=True))[1], "risk_score_range")

	def test_scorer_version_below_one(self):
		risk = _valid_risk()
		risk["scorer_version"] = 0
		self.assertEqual(mirrors.validate_risk_object(risk)[1], "risk_scorer_version")

	def test_band_not_string(self):
		risk = _valid_risk()
		risk["band"] = 5
		self.assertEqual(mirrors.validate_risk_object(risk)[1], "risk_band_type")

	def test_computed_at_unparseable(self):
		risk = _valid_risk()
		risk["computed_at"] = "not-a-timestamp"
		self.assertEqual(mirrors.validate_risk_object(risk)[1], "risk_computed_at")

	def test_breakdown_not_list(self):
		risk = _valid_risk()
		risk["breakdown"] = {"oops": 1}
		self.assertEqual(mirrors.validate_risk_object(risk)[1], "risk_breakdown_not_list")

	def test_value_wrong_type(self):
		risk = _valid_risk()
		risk["breakdown"][0]["value"] = [1, 2, 3]
		self.assertEqual(mirrors.validate_risk_object(risk)[1], "risk_value_type")

	def test_weight_negative(self):
		risk = _valid_risk()
		risk["breakdown"][0]["weight"] = -1
		self.assertEqual(mirrors.validate_risk_object(risk)[1], "risk_weight")

	def test_contribution_exceeds_weight(self):
		risk = _valid_risk()
		risk["breakdown"][0]["weight"] = 10
		risk["breakdown"][0]["contribution"] = 11
		self.assertEqual(mirrors.validate_risk_object(risk)[1], "risk_contribution_range")

	def test_reason_not_string(self):
		risk = _valid_risk()
		risk["breakdown"][0]["reason"] = 42
		self.assertEqual(mirrors.validate_risk_object(risk)[1], "risk_reason_type")

	def test_warnings_unknown_band_no_values(self):
		risk = _valid_risk(band="BLOCK")
		warnings = mirrors.risk_warnings(risk)
		self.assertIn("unknown_band:BLOCK", warnings)
		# warnings never carry transaction/score values
		self.assertTrue(
			all(":" not in w or w.startswith(("unknown_band:", "unknown_signal:")) for w in warnings)
		)

	def test_warnings_known_band_and_signals_empty(self):
		self.assertEqual(mirrors.risk_warnings(_valid_risk()), [])

	def test_collect_risk_warnings_dedup_sorted(self):
		recent = [
			_item("a", risk=_valid_risk(signal="zeta_signal")),
			_item("b", risk=_valid_risk(signal="zeta_signal", band="BLOCK")),
			_item("c", state="COMPLETED"),  # no risk → ignored
		]
		codes = mirrors._collect_risk_warnings(recent)
		self.assertEqual(codes, ["unknown_band:BLOCK", "unknown_signal:zeta_signal"])

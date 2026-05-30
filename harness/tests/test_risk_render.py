"""G2 — pure unit tests for the risk-render helpers (no DB, no frappe).

Forward-compat is the contract: unknown signals, unknown bands, and unexpected value types
must RENDER, never raise. The G2.6 gate is `test_render_unknown_signal_nonempty`.
"""

import unittest

from harness.koya_harness import risk_render as R


def _row(signal="amount_vs_kyc_tier", value="95000", weight=25, contribution=23, reason="r"):
	return {
		"signal": signal,
		"value": value,
		"weight": weight,
		"contribution": contribution,
		"reason": reason,
	}


class TestRiskRender(unittest.TestCase):
	# ---- the G2.6 gate -----------------------------------------------------
	def test_render_unknown_signal_nonempty(self):
		out = R.render_breakdown_html([_row(signal="totally_unknown_signal", value={"x": 1}, contribution=0)])
		self.assertIsInstance(out, str)
		self.assertTrue(out)
		self.assertIn("totally_unknown_signal", out)

	def test_render_empty_breakdown_nonempty(self):
		out = R.render_breakdown_html([])
		self.assertTrue(out)
		self.assertIn("No breakdown signals", out)

	def test_render_invalid_breakdown_nonempty(self):
		self.assertTrue(R.render_breakdown_html("not a list"))
		self.assertTrue(R.render_breakdown_html(None))

	def test_render_zero_contribution_row_muted_not_hidden(self):
		out = R.render_breakdown_html(
			[_row(signal="first_transaction", value=False, weight=10, contribution=0)]
		)
		self.assertIn("first_transaction", out)  # present, not filtered
		self.assertIn("krq-bd-row--muted", out)  # de-emphasized

	def test_render_escapes_html(self):
		out = R.render_breakdown_html([_row(reason="<script>alert(1)</script>")])
		self.assertNotIn("<script>", out)
		self.assertIn("&lt;script&gt;", out)

	# ---- value dispatch ----------------------------------------------------
	def test_value_money(self):
		self.assertEqual(R.value_for_signal("amount_vs_kyc_tier", "95000"), "KES 95,000")
		self.assertEqual(R.value_for_signal("velocity_volume_24h", 95000.0), "KES 95,000")
		self.assertEqual(R.value_for_signal("amount_vs_kyc_tier", "95000.50"), "KES 95,000.50")

	def test_value_count(self):
		self.assertEqual(R.value_for_signal("velocity_count_24h", 8), "8")
		self.assertEqual(R.value_for_signal("velocity_count_24h", "8"), "8")
		self.assertEqual(R.value_for_signal("structuring_pattern", 1500), "1,500")

	def test_value_boolean(self):
		self.assertEqual(R.value_for_signal("first_transaction", True), "Yes")
		self.assertEqual(R.value_for_signal("first_transaction", False), "No")
		self.assertEqual(R.value_for_signal("session_anomaly", "true"), "Yes")
		self.assertEqual(R.value_for_signal("session_anomaly", 0), "No")

	def test_value_null_renders_dash(self):
		self.assertEqual(R.value_for_signal("amount_vs_kyc_tier", None), "—")
		self.assertEqual(R.value_for_signal("velocity_count_24h", None), "—")
		self.assertEqual(R.value_for_signal("first_transaction", None), "—")
		self.assertEqual(R.value_for_signal("future_signal", None), "—")

	def test_value_unknown_signal_raw(self):
		self.assertEqual(R.value_for_signal("future_signal", "anything"), "anything")
		self.assertEqual(R.value_for_signal("future_signal", 42), "42")

	def test_value_unexpected_type_no_crash(self):
		# money / count signals fed a non-numeric type → raw verbatim, never raises.
		self.assertEqual(R.value_for_signal("amount_vs_kyc_tier", [1, 2]), "[1, 2]")
		self.assertEqual(R.value_for_signal("velocity_count_24h", {"a": 1}), "{'a': 1}")

	def test_format_kes(self):
		self.assertEqual(R.format_kes("95000"), "KES 95,000")
		self.assertEqual(R.format_kes(95000.5), "KES 95,000.50")
		self.assertEqual(R.format_kes(None), "—")
		self.assertEqual(R.format_kes("abc"), "abc")
		self.assertEqual(R.format_kes(True), "True")  # bool is not a money value

	# ---- band class --------------------------------------------------------
	def test_band_class(self):
		self.assertEqual(R.band_class("REVIEW"), "review")
		self.assertEqual(R.band_class("PASS"), "pass")
		self.assertEqual(R.band_class("FAIL"), "other")
		self.assertEqual(R.band_class(None), "other")

	# ---- sort / top --------------------------------------------------------
	def test_sort_contribution_desc_zero_retained(self):
		rows = [_row(contribution=0), _row(contribution=23), _row(contribution=8)]
		ordered = R.sort_breakdown(rows)
		self.assertEqual([r["contribution"] for r in ordered], [23, 8, 0])  # zero retained

	def test_sort_drops_non_dict_rows(self):
		ordered = R.sort_breakdown([_row(contribution=5), "bad", 7])
		self.assertEqual(len(ordered), 1)

	def test_sort_stable_for_ties(self):
		rows = [_row(signal="a", contribution=5), _row(signal="b", contribution=5)]
		ordered = R.sort_breakdown(rows)
		self.assertEqual([r["signal"] for r in ordered], ["a", "b"])

	def test_top_signal_picks_max(self):
		rows = [
			_row(signal="a", contribution=8),
			_row(signal="b", contribution=23),
			_row(signal="c", contribution=0),
		]
		self.assertEqual(R.top_signal(rows)["signal"], "b")

	def test_top_signal_empty_or_invalid_none(self):
		self.assertIsNone(R.top_signal([]))
		self.assertIsNone(R.top_signal("nope"))


if __name__ == "__main__":
	unittest.main()

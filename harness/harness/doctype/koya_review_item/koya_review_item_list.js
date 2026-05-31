// Koya Review Item — standard List view, colored by hold type.
//
// The standard list gives clickable rows -> form, sort, filter, pagination, scroll, and the
// sidebar for free. get_indicator colors the row by hold_reason (the operational dimension):
// delivery holds are post-payment (money in) -> red/heaviest; risk + compliance are pre-payment.

frappe.listview_settings["Koya Review Item"] = {
	add_fields: ["hold_reason", "risk_band", "has_risk", "risk_score", "state"],
	get_indicator: function (doc) {
		const map = {
			btc_delivery_retry_exhausted: [__("Delivery — PAYMENT IN"), "red"],
			risk_review_required: [__("Risk review"), "orange"],
			compliance_review_required: [__("Compliance review"), "blue"],
		};
		const hr = doc.hold_reason;
		if (hr && map[hr]) return [map[hr][0], map[hr][1], "hold_reason,=," + hr];
		if (doc.risk_band === "REVIEW") return [__("Risk review"), "orange", "risk_band,=,REVIEW"];
		return [__(hr || doc.state || "Held"), "gray", ""];
	},
};

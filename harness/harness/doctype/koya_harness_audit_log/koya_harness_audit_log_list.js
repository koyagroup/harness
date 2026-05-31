// Koya Harness Audit Log — standard List view for the raw append-only audit trail.
//
// The "System events" link on the decision-history page routes here (filtered). Standard list
// gives click / sort / filter / scroll / saved-filters for free; get_indicator colors by outcome.
// The paired (sent<->response) decision view lives on the custom decision-history page; this is
// the raw event browse.

frappe.listview_settings["Koya Harness Audit Log"] = {
	add_fields: ["outcome", "event_type"],
	get_indicator: function (doc) {
		const map = {
			success: ["Success", "green"],
			warning: ["Warning", "orange"],
			failure: ["Failure", "red"],
		};
		const o = (doc.outcome || "").toLowerCase();
		if (map[o]) return [__(map[o][0]), map[o][1], "outcome,=," + doc.outcome];
		return [__(doc.outcome || "—"), "gray", ""];
	},
};

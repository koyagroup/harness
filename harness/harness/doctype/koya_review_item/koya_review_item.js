// Koya Review Item — enriched standard Form.
//
// The doctype is read-only (a snapshot row); this form script adds the bespoke decision surface
// on top of the free standard form: a hold-reason banner, the risk breakdown (only when the hold
// was risk-scored), and Approve/Reject buttons that POST a SIGNED decision to Koya via the
// existing, money-gated send path. All render data + the reason-aware confirmation copy come from
// the existing server endpoint `review_item_detail` (single-sourced with decision_render) — the JS
// fabricates nothing. The real money-path gate is server-side (_require_decision_role); `can_decide`
// only decides whether to draw the buttons (defense-in-depth).

frappe.ui.form.on("Koya Review Item", {
	refresh(frm) {
		frappe.call({
			method: "harness.koya_harness.api.review.review_item_detail",
			args: { name: frm.doc.name },
			callback: (r) => {
				const d = r && r.message;
				if (!d || !d.permitted || d.found === false) return;
				render_banner(frm, d);
				render_breakdown(frm, d);
				if (d.can_decide) add_decision_buttons(frm, d);
			},
		});
	},
});

function render_banner(frm, d) {
	const $w = frm.get_field("hold_reason_html").$wrapper;
	if (!d.hold_reason_label) {
		$w.empty();
		return;
	}
	const color = { postpay: "red", prepay: "orange" }[d.hold_reason_class] || "gray";
	$w.html(`
		<div class="form-message ${color === "red" ? "red" : color === "orange" ? "yellow" : "blue"}"
			style="font-weight:600;">${frappe.utils.escape_html(d.hold_reason_label)}</div>
	`);
}

function render_breakdown(frm, d) {
	const $w = frm.get_field("risk_breakdown_html").$wrapper;
	if (d.has_risk) {
		$w.html(d.breakdown_html || "");
	} else {
		$w.html(
			`<div class="text-muted" style="padding:8px 2px;">${frappe.utils.escape_html(
				d.no_risk_note || "",
			)}</div>`,
		);
	}
}

function add_decision_buttons(frm, d) {
	frm
		.add_custom_button(__("Approve"), () => {
			frappe.confirm(d.confirm_approve, () => send_decision(frm, "APPROVE", null));
		})
		.removeClass("btn-default")
		.addClass("btn-success");

	frm
		.add_custom_button(__("Reject"), () => {
			const dlg = new frappe.ui.Dialog({
				title: __("Reject this conversion"),
				fields: [
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Reason (required)"),
						reqd: 1,
					},
				],
				primary_action_label: __("Continue"),
				primary_action: (values) => {
					const reason = (values.reason || "").trim();
					if (!reason) {
						frappe.msgprint(__("A reason is required to reject."));
						return;
					}
					dlg.hide();
					// reason-aware confirmation (server-supplied copy; heaviest for delivery holds)
					frappe.confirm(d.confirm_reject, () => send_decision(frm, "REJECT", reason));
				},
			});
			dlg.show();
		})
		.removeClass("btn-default")
		.addClass("btn-danger");
}

function send_decision(frm, decision, reason) {
	frappe.call({
		method: "harness.koya_harness.api.settlement.send_settlement_decision",
		args: { session_ref: frm.doc.ref, decision: decision, reason: reason },
		freeze: true,
		freeze_message: __("Sending decision…"),
		callback: (r) => {
			const res = r && r.message;
			if (!res) return;
			const indicator =
				res.severity === "error" ? "red" : res.severity === "warning" ? "orange" : "green";
			let msg = frappe.utils.escape_html(res.message || "");
			if (res.resulting_label) msg += "<br>" + frappe.utils.escape_html(res.resulting_label);
			frappe.msgprint({ title: __("Decision result"), message: msg, indicator: indicator });
			// An accepted decision leaves the queue on the next mirror snapshot (skip-flag).
			frm.reload_doc();
		},
	});
}

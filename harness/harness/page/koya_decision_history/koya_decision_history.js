// Koya Decision History — read-only compliance trail of settlement decisions.
//
// Boundary: READS harness.koya_harness.api.audit_view.decision_history only. NO actions, NO
// decision-making, NO calls to Koya — this is history, not a place to make or undo decisions.
// Role-gated to System Manager + koya_harness_compliance (the page roles + the server gate).
// Decision events ONLY; system (mirror/health) events live separately — the "System events"
// link routes to the raw audit-log list filtered to those event types.
//
// Value-free: the audit never stored raw reason text / amounts / PII; this view renders only
// what the API returns and never fabricates it.

frappe.pages["koya-decision-history"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Koya Decision History"),
		single_column: true,
	});

	kdh_inject_styles();

	const $root = $(`<div class="kdh-wrap"></div>`).appendTo(page.body);
	page.set_secondary_action(__("Refresh"), () => load(), "refresh");

	const SYSTEM_EVENTS = [
		"mirror_rates_received",
		"mirror_transactions_received",
		"mirror_risk_validation_warning",
		"health_ping_received",
	];

	const filters = {};

	function current_filters() {
		const f = {};
		$root.find("[data-filter]").each(function () {
			const k = $(this).attr("data-filter");
			const v = ($(this).val() || "").trim();
			if (v) f[k] = v;
		});
		return f;
	}

	function load() {
		frappe.call({
			method: "harness.koya_harness.api.audit_view.decision_history",
			args: { filters: current_filters(), limit: 200 },
			callback: (r) => {
				if (r && r.message) paint(r.message);
			},
		});
	}

	function paint(data) {
		if (!data.permitted) {
			$root.html(`<div class="kdh-empty">${__("You do not have access to the decision history.")}</div>`);
			return;
		}
		const rows = (data.records || []).map(row_html).join("");
		const table = rows
			? `<div class="kdh-tablewrap"><table class="kdh-table"><thead><tr>
					<th>${__("Session")}</th><th>${__("Decision")}</th><th>${__("Hold reason")}</th>
					<th>${__("Reviewer")}</th><th>${__("Decided")}</th><th>${__("Resulting state")}</th>
					<th>${__("Outcome")}</th><th>${__("Idempotent")}</th>
				</tr></thead><tbody>${rows}</tbody></table></div>`
			: `<div class="kdh-empty">${__("No settlement decisions recorded yet.")}</div>`;

		$root.html(`
			<div class="kdh-head">
				<div class="kdh-title">${__("Decision History")} · ${esc(data.count)}</div>
				<a class="kdh-link" data-sysevents href="#">${__("System events")} →</a>
			</div>
			${filter_bar()}
			${table}
		`);
		$root.find("[data-apply]").on("click", () => load());
		$root.find("[data-filter]").on("change", () => load());
		$root.find("[data-sysevents]").on("click", (e) => {
			e.preventDefault();
			frappe.route_options = { event_type: ["in", SYSTEM_EVENTS] };
			frappe.set_route("List", "Koya Harness Audit Log");
		});
	}

	function filter_bar() {
		return `
			<div class="kdh-filters">
				<select class="form-control input-sm" data-filter="decision">
					<option value="">${__("All decisions")}</option>
					<option value="APPROVE">${__("Approve")}</option>
					<option value="REJECT">${__("Reject")}</option>
				</select>
				<select class="form-control input-sm" data-filter="outcome">
					<option value="">${__("All outcomes")}</option>
					<option value="success">${__("Success")}</option>
					<option value="warning">${__("Warning")}</option>
					<option value="failure">${__("Failure")}</option>
				</select>
				<select class="form-control input-sm" data-filter="hold_reason">
					<option value="">${__("All hold reasons")}</option>
					<option value="risk_review_required">${__("Risk")}</option>
					<option value="compliance_review_required">${__("Compliance")}</option>
					<option value="btc_delivery_retry_exhausted">${__("Delivery (post-payment)")}</option>
				</select>
				<input type="date" class="form-control input-sm" data-filter="from_date" title="${__("From")}">
				<input type="date" class="form-control input-sm" data-filter="to_date" title="${__("To")}">
				<button class="btn btn-sm btn-default" data-apply>${__("Apply")}</button>
			</div>`;
	}

	function row_html(r) {
		const dec = (r.decision || "—").toUpperCase();
		const dec_cls = dec === "APPROVE" ? "approve" : dec === "REJECT" ? "reject" : "other";
		// REFUND_PENDING reads distinctly — a reject that booked a refund obligation.
		const refund = r.resulting_state === "REFUND_PENDING";
		const state_cls = refund ? "refund" : "";
		const out = (r.outcome || "").toLowerCase();
		const out_cls = out === "success" ? "ok" : out === "warning" ? "warn" : out ? "fail" : "pending";
		const pending = r.status === "pending";
		return `<tr class="${pending ? "kdh-row--pending" : ""}">
			<td><span class="kdh-ref">${esc(r.session_ref)}</span></td>
			<td><span class="kdh-badge kdh-badge--${dec_cls}">${esc(dec)}</span></td>
			<td>${esc(r.hold_reason_label || r.hold_reason || "—")}</td>
			<td>${esc(r.reviewer || "—")}</td>
			<td>${esc(r.decided_at || "—")}</td>
			<td class="kdh-state ${state_cls}">${esc(
				pending ? __("awaiting response…") : r.resulting_label || r.resulting_state || "—",
			)}</td>
			<td><span class="kdh-badge kdh-badge--${out_cls}">${esc(
				pending ? __("pending") : out || "—",
			)}${r.error_code ? " · " + esc(r.error_code) : ""}</span></td>
			<td>${r.idempotent ? __("yes") : ""}</td>
		</tr>`;
	}

	load();
	$(wrapper).on("show", () => load());
};

function esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

function kdh_inject_styles() {
	if (document.getElementById("kdh-styles")) return;
	const css = `
		.kdh-wrap { padding: 8px 4px 24px; }
		.kdh-wrap, .kdh-wrap * { box-sizing: border-box; }
		.kdh-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
		.kdh-title { font-size: 16px; font-weight: 600; }
		.kdh-link { font-size: 12.5px; font-weight: 600; cursor: pointer; }
		.kdh-filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; align-items: center; }
		.kdh-filters .form-control { width: auto; min-width: 130px; }
		.kdh-tablewrap { width: 100%; overflow-x: auto; }
		.kdh-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
		.kdh-table th { text-align: left; color: var(--text-muted); font-weight: 600; padding: 6px 8px;
			border-bottom: 1px solid var(--border-color); white-space: nowrap; }
		.kdh-table td { padding: 7px 8px; border-bottom: 1px solid var(--border-color); white-space: nowrap; }
		.kdh-ref { font-weight: 600; }
		.kdh-row--pending { opacity: 0.75; }
		.kdh-state.refund { color: #8a1f11; font-weight: 600; }
		.kdh-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 12px; letter-spacing: 0.03em; }
		.kdh-badge--approve { color: #1a7f4b; background: rgba(26,127,75,0.12); }
		.kdh-badge--reject { color: #8a1f11; background: rgba(193,42,28,0.12); }
		.kdh-badge--other { color: var(--text-muted); background: var(--control-bg, rgba(125,125,125,0.12)); }
		.kdh-badge--ok { color: #1a7f4b; background: rgba(26,127,75,0.10); }
		.kdh-badge--warn { color: #9a6700; background: rgba(212,167,44,0.16); }
		.kdh-badge--fail { color: #8a1f11; background: rgba(193,42,28,0.14); }
		.kdh-badge--pending { color: var(--text-muted); background: var(--control-bg, rgba(125,125,125,0.12)); }
		.kdh-empty { color: var(--text-muted); font-size: 12.5px; padding: 14px 2px; }
	`;
	$(`<style id="kdh-styles">${css}</style>`).appendTo(document.head);
}

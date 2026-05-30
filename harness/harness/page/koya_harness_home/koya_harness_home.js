// Koya Operations Console — the harness's single staff entry point.
//
// Combines three sections: Mirror Status (both roles), Review Queue (compliance only),
// and an Audit Log link (either role). Role-gating is per SECTION: an ops user must NOT
// see the Review Queue section at all. This is enforced two ways — the section is not
// rendered unless the user has koya_harness_compliance (or System Manager), AND its data
// comes from review_queue_state, which is permission-gated server-side. Read-only: no
// actions, no writes, no calls to Koya.

frappe.pages["koya-harness-home"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Koya Operations Console"),
		single_column: true,
	});

	khh_inject_styles();

	const roles = frappe.user_roles || [];
	const is_admin = roles.includes("System Manager");
	const is_compliance = is_admin || roles.includes("koya_harness_compliance");
	const is_ops = is_admin || roles.includes("koya_harness_ops");
	const can_audit = is_compliance || is_ops;

	const $root = $(`<div class="khh-wrap"></div>`).appendTo(page.body);
	page.set_secondary_action(__("Refresh"), () => load(), "refresh");

	render_skeleton();

	let timer = null;

	function render_skeleton() {
		$root.html(`
			<div class="khh-banner">
				<div>
					<div class="khh-brand">${__("Koya Operations Console")}</div>
					<div class="khh-brand-sub">${__("Harness control plane · display & review · read-only")}</div>
				</div>
				<div class="khh-conn" data-conn><span class="khh-pill khh-pill--neutral">${__("Connecting…")}</span></div>
			</div>

			<div class="khh-section">
				<div class="khh-h">${__("Mirror Status")}</div>
				<div data-mirror class="khh-mirror">${__("Loading…")}</div>
			</div>

			${
				is_compliance
					? `<div class="khh-section">
						<div class="khh-h">${__("Review Queue")}</div>
						<div data-review class="khh-review">${__("Loading…")}</div>
					</div>`
					: ""
			}

			${
				can_audit
					? `<div class="khh-section">
						<div class="khh-h">${__("Audit Log")}</div>
						<div class="khh-audit">
							<a class="khh-link" data-audit href="#">${__("Open audit log")} →</a>
						</div>
					</div>`
					: ""
			}
		`);
		$root.find("[data-audit]").on("click", (e) => {
			e.preventDefault();
			frappe.set_route("List", "Koya Harness Audit Log");
		});
	}

	function load() {
		frappe.call({
			method: "harness.koya_harness.api.mirrors.display_state",
			callback: (r) => {
				if (r && r.message) render_mirror(r.message);
			},
		});
		if (is_compliance) {
			frappe.call({
				method: "harness.koya_harness.api.review.review_queue_state",
				callback: (r) => {
					if (r && r.message) render_review(r.message);
				},
			});
		}
	}

	function freshest_age(d) {
		const ages = [];
		if (d.rates && d.rates.age_seconds != null) ages.push(d.rates.age_seconds);
		if (d.transactions && d.transactions.age_seconds != null) ages.push(d.transactions.age_seconds);
		return ages.length ? Math.min(...ages) : null;
	}

	function render_mirror(d) {
		// Banner connection pill: freshest push age across both mirrors.
		const age = freshest_age(d);
		const any_fresh = (d.rates && !d.rates.stale) || (d.transactions && !d.transactions.stale);
		let conn;
		if (age == null) {
			conn = `<span class="khh-pill khh-pill--neutral">${__("Awaiting first push…")}</span>`;
		} else if (any_fresh) {
			conn = `<span class="khh-pill khh-pill--live">${__("Live")} · ${esc(fmt_age(age))}</span>`;
		} else {
			conn = `<span class="khh-pill khh-pill--stale">${__("Stale")} · ${esc(fmt_age(age))}</span>`;
		}
		$root.find("[data-conn]").html(conn);

		const rates = d.rates || {};
		const txns = d.transactions || {};
		const mr = (txns.status_counts && txns.status_counts.MANUAL_REVIEW) || 0;
		$root.find("[data-mirror]").html(`
			<div class="khh-cards">
				<div class="khh-card">
					<div class="khh-card-row"><span>${__("Rates")}</span>${mirror_pill(rates)}</div>
					<div class="khh-card-sub">${esc((rates.rates || []).length)} ${__("pairs")} · ${__("source")}: ${
						esc(rates.last_source) || "—"
					}</div>
				</div>
				<div class="khh-card">
					<div class="khh-card-row"><span>${__("Transactions")}</span>${mirror_pill(txns)}</div>
					<div class="khh-card-sub">${esc(txns.recent_count || 0)} ${__("recent")} · ${esc(
						mr,
					)} ${__("in manual review")}</div>
				</div>
			</div>
			<div class="khh-linkrow"><a class="khh-link" data-mirrorpage href="#">${__(
				"Open mirror status",
			)} →</a></div>
		`);
		$root.find("[data-mirrorpage]").on("click", (e) => {
			e.preventDefault();
			frappe.set_route("koya-mirror-status");
		});
	}

	function render_review(d) {
		if (!d || !d.permitted) {
			$root.find("[data-review]").html(`<div class="khh-muted">${__("No access.")}</div>`);
			return;
		}
		$root.find("[data-review]").html(`
			<div class="khh-card">
				<div class="khh-card-row">
					<span>${__("Pending manual review")}: <b>${esc(d.count)}</b></span>
					${queue_pill(d)}
				</div>
			</div>
			<div class="khh-linkrow"><a class="khh-link" data-reviewpage href="#">${__(
				"Open review queue",
			)} →</a></div>
		`);
		$root.find("[data-reviewpage]").on("click", (e) => {
			e.preventDefault();
			frappe.set_route("koya-review-queue");
		});
	}

	load();
	timer = setInterval(load, 15000);
	$(wrapper).on("hide", () => timer && clearInterval(timer));
};

function esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

function fmt_age(sec) {
	if (sec == null) return "—";
	if (sec < 60) return `${sec}s ago`;
	if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
	return `${Math.floor(sec / 3600)}h ago`;
}

function mirror_pill(m) {
	if (m.never_received) {
		return `<span class="khh-pill khh-pill--neutral">${__("Awaiting…")}</span>`;
	}
	if (m.stale) {
		return `<span class="khh-pill khh-pill--stale">${__("Stale")} · ${esc(fmt_age(m.age_seconds))}</span>`;
	}
	return `<span class="khh-pill khh-pill--live">${__("Live")} · ${esc(fmt_age(m.age_seconds))}</span>`;
}

function queue_pill(d) {
	if (d.never_received) {
		return `<span class="khh-pill khh-pill--neutral">${__("Awaiting…")}</span>`;
	}
	if (d.stale) {
		return `<span class="khh-pill khh-pill--stale">${__("Stale")} · ${esc(fmt_age(d.age_seconds))}</span>`;
	}
	return `<span class="khh-pill khh-pill--live">${__("Live")} · ${esc(fmt_age(d.age_seconds))}</span>`;
}

function khh_inject_styles() {
	if (document.getElementById("khh-styles")) return;
	const css = `
		.khh-wrap { padding: 8px 4px 24px; }
		.khh-banner { display: flex; align-items: center; justify-content: space-between; gap: 16px;
			background: var(--card-bg, var(--fg-color)); border: 1px solid var(--border-color);
			border-radius: var(--border-radius-lg, 10px); padding: 18px 20px; margin-bottom: 20px; }
		.khh-brand { font-size: 20px; font-weight: 800; }
		.khh-brand-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
		.khh-section { margin-bottom: 22px; }
		.khh-h { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
			color: var(--text-muted); margin-bottom: 10px; }
		.khh-cards { display: grid; grid-template-columns: 1fr; gap: 12px; }
		@media (min-width: 800px) { .khh-cards { grid-template-columns: 1fr 1fr; } }
		.khh-card { background: var(--card-bg, var(--fg-color)); border: 1px solid var(--border-color);
			border-radius: var(--border-radius-lg, 10px); padding: 14px 16px; }
		.khh-card-row { display: flex; align-items: center; justify-content: space-between; gap: 10px;
			font-size: 14px; font-weight: 600; }
		.khh-card-sub { color: var(--text-muted); font-size: 12px; margin-top: 6px; }
		.khh-pill { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 20px; white-space: nowrap; }
		.khh-pill--live { color: #1a7f4b; background: rgba(26,127,75,0.10); }
		.khh-pill--stale { color: #9a6700; background: rgba(212,167,44,0.16); }
		.khh-pill--neutral { color: var(--text-muted); background: var(--control-bg, rgba(125,125,125,0.12)); }
		.khh-linkrow { margin-top: 10px; }
		.khh-link { font-size: 12.5px; font-weight: 600; cursor: pointer; }
		.khh-muted { color: var(--text-muted); font-size: 12.5px; }
	`;
	$(`<style id="khh-styles">${css}</style>`).appendTo(document.head);
}

// Koya Review Queue — read-only compliance console for MANUAL_REVIEW conversions.
//
// Boundary: this page only READS via harness.koya_harness.api.review.*. It NEVER writes,
// NEVER calls Koya, and exposes NO approve/reject/edit actions — reviewers can see the
// risk data but cannot act on it yet (that is Phase 4). The queue is a snapshot rebuilt
// by the transactions mirror on every push.
//
// Two views, route-driven: #koya-review-queue (list) and #koya-review-queue/<ref> (detail).
// Stale UX is reused from the Phase-2 mirror status page: informational amber, never alarm.

frappe.pages["koya-review-queue"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Koya Review Queue"),
		single_column: true,
	});

	krq_inject_styles();

	const $root = $(`<div class="krq-wrap"></div>`).appendTo(page.body);
	page.set_secondary_action(__("Refresh"), () => route_render(), "refresh");

	let timer = null;

	function on_this_page() {
		const r = frappe.get_route();
		return r && r[0] === "koya-review-queue";
	}

	function current_ref() {
		const r = frappe.get_route();
		return on_this_page() && r[1] ? r[1] : null;
	}

	function route_render() {
		if (!on_this_page()) return;
		const ref = current_ref();
		if (ref) {
			render_detail(ref);
		} else {
			render_list();
		}
	}

	function render_list() {
		frappe.call({
			method: "harness.koya_harness.api.review.review_queue_state",
			callback: (r) => {
				if (!on_this_page() || current_ref()) return; // route changed mid-call
				if (r && r.message) paint_list(r.message);
			},
		});
	}

	function paint_list(data) {
		if (!data.permitted) {
			$root.html(`<div class="krq-empty">${__("You do not have access to the review queue.")}</div>`);
			return;
		}
		const rows = (data.items || [])
			.map(
				(it) => `<tr class="krq-row" data-ref="${esc(it.ref)}">
				<td><span class="krq-ref">${esc(it.ref)}</span></td>
				<td>${esc(it.asset)}</td>
				<td class="krq-num">${esc(it.kes_display)}</td>
				<td>${esc(it.score == null ? "—" : it.score)} ${band_badge(it.band, it.band_class)}</td>
				<td class="krq-reason">${esc(it.top_reason)}</td>
				<td>${esc(fmt_age(it.age_seconds))}</td>
			</tr>`,
			)
			.join("");

		const table = rows
			? `<div class="krq-tablewrap"><table class="krq-table"><thead><tr>
					<th>${__("Ref")}</th><th>${__("Asset")}</th>
					<th class="krq-num">${__("KES")}</th><th>${__("Score")}</th>
					<th>${__("Top signal")}</th><th>${__("Age")}</th>
				</tr></thead><tbody>${rows}</tbody></table></div>`
			: `<div class="krq-empty">${__("No conversions are currently in manual review.")}</div>`;

		$root.html(`
			<div class="krq-head">
				<div class="krq-title">${__("Manual Review")} · ${esc(data.count)}</div>
				${queue_pill(data)}
			</div>
			<div class="krq-sub">${__("Last update")}: ${esc(data.last_received_at) || "—"}</div>
			${table}
		`);

		$root.find(".krq-row").on("click", function () {
			frappe.set_route("koya-review-queue", $(this).attr("data-ref"));
		});
	}

	function render_detail(ref) {
		frappe.call({
			method: "harness.koya_harness.api.review.review_item_detail",
			args: { name: ref },
			callback: (r) => {
				if (current_ref() !== ref) return; // route changed mid-call
				if (r && r.message) paint_detail(r.message);
			},
		});
	}

	function paint_detail(d) {
		if (!d.permitted) {
			$root.html(`<div class="krq-empty">${__("You do not have access to this item.")}</div>`);
			return;
		}
		if (d.found === false) {
			$root.html(`
				<div class="krq-back" data-back="1">← ${__("Back to queue")}</div>
				<div class="krq-empty">${__("This item is no longer in the review queue.")}</div>`);
			$root.find("[data-back]").on("click", () => frappe.set_route("koya-review-queue"));
			return;
		}

		$root.html(`
			<div class="krq-back" data-back="1">← ${__("Back to queue")}</div>
			${
				d.hold_reason_label
					? `<div class="krq-hold krq-hold--${esc(d.hold_reason_class)}">${esc(d.hold_reason_label)}</div>`
					: ""
			}
			<div class="krq-detail-card">
				${
					d.has_risk
						? `<div class="krq-score-wrap">
							<div class="krq-score">${esc(d.score == null ? "—" : d.score)} <span class="krq-score-max">/ 100</span></div>
							${band_badge(d.band, d.band_class)}
							<div class="krq-caption">${esc(d.scorer_caption)}</div>
							<div class="krq-caption">${__("Computed")} ${esc(d.computed_at_relative)}</div>
						</div>`
						: `<div class="krq-score-wrap krq-norisk">${esc(d.no_risk_note)}</div>`
				}
				<div class="krq-scalars">
					${scalar(__("Ref"), d.ref)}
					${scalar(__("State"), d.state)}
					${scalar(__("Asset"), d.asset)}
					${scalar(__("KES Amount"), d.kes_display)}
					${scalar(__("Asset Amount"), d.asset_amount)}
					${scalar(__("Created"), d.created_at)}
					${scalar(__("Updated"), d.updated_at)}
				</div>
			</div>
			${
				d.has_risk
					? `<div class="krq-bd-title">${__("Risk breakdown")}</div>
						<div class="krq-bd-host">${d.breakdown_html || ""}</div>`
					: ""
			}
			${d.can_decide ? decision_panel() : ""}
		`);
		$root.find("[data-back]").on("click", () => frappe.set_route("koya-review-queue"));
		if (d.can_decide) wire_decision(d);
	}

	// The approve/reject affordance is drawn ONLY when the server says this user may decide
	// (defence-in-depth — the real money-path gate is server-side on the send method). Reject
	// requires a non-empty reason; both decisions go through a reason-aware confirmation whose
	// text the SERVER supplies (single-sourced with the Python decision_render helpers).
	function decision_panel() {
		return `
			<div class="krq-decision" data-decision-panel="1">
				<div class="krq-decision-actions">
					<button class="btn btn-sm btn-success" data-act="approve">${__("Approve")}</button>
					<button class="btn btn-sm btn-danger" data-act="reject">${__("Reject")}</button>
				</div>
				<div class="krq-reject-form" style="display:none;">
					<textarea class="form-control krq-reject-reason" rows="2"
						placeholder="${__("Reason (required to reject)")}"></textarea>
					<div class="krq-reject-actions">
						<button class="btn btn-sm btn-danger" data-act="reject-confirm">${__("Submit rejection")}</button>
						<button class="btn btn-sm btn-default" data-act="reject-cancel">${__("Cancel")}</button>
					</div>
				</div>
				<div class="krq-decision-result" style="display:none;"></div>
			</div>`;
	}

	function wire_decision(d) {
		const $panel = $root.find("[data-decision-panel]");
		$panel.find('[data-act="approve"]').on("click", () => {
			frappe.confirm(d.confirm_approve, () => send_decision(d, "APPROVE", null));
		});
		$panel.find('[data-act="reject"]').on("click", () => {
			$panel.find(".krq-reject-form").show();
			$panel.find(".krq-reject-reason").trigger("focus");
		});
		$panel.find('[data-act="reject-cancel"]').on("click", () => {
			$panel.find(".krq-reject-form").hide();
		});
		$panel.find('[data-act="reject-confirm"]').on("click", () => {
			const reason = ($panel.find(".krq-reject-reason").val() || "").trim();
			if (!reason) {
				frappe.msgprint(__("A reason is required to reject."));
				return;
			}
			frappe.confirm(d.confirm_reject, () => send_decision(d, "REJECT", reason));
		});
	}

	function send_decision(d, decision, reason) {
		const $panel = $root.find("[data-decision-panel]");
		$panel.find("button").prop("disabled", true); // double-submit guard
		frappe.call({
			method: "harness.koya_harness.api.settlement.send_settlement_decision",
			args: { session_ref: d.ref, decision: decision, reason: reason },
			callback: (r) => {
				const res = r && r.message;
				const $result = $panel.find(".krq-decision-result");
				if (!res) {
					$panel.find("button").prop("disabled", false);
					return;
				}
				const sev = res.severity || "info";
				$result
					.attr("class", "krq-decision-result krq-result--" + esc(sev))
					.show()
					.html(
						esc(res.message) +
							(res.resulting_label
								? `<div class="krq-result-state">${esc(res.resulting_label)}</div>`
								: ""),
					);
				$panel.find(".krq-reject-form").hide();
				if (res.ok) {
					// Accepted / idempotent: the item leaves the queue on the next snapshot
					// (Koya's skip-flag). Hide the actions so it cannot be re-submitted.
					$panel.find(".krq-decision-actions").hide();
				} else {
					// Conflict / error / transport — let the reviewer retry (idempotency is safe).
					$panel.find("button").prop("disabled", false);
				}
			},
			error: () => {
				$panel.find("button").prop("disabled", false);
				$panel
					.find(".krq-decision-result")
					.attr("class", "krq-decision-result krq-result--warning")
					.show()
					.text(__("The decision may not have landed — check the state and retry."));
			},
		});
	}

	route_render();
	timer = setInterval(() => {
		if (on_this_page() && !current_ref()) render_list();
	}, 15000);

	frappe.router.on("change", route_render);
	$(wrapper).on("hide", () => timer && clearInterval(timer));
};

function esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

function scalar(label, value) {
	return `<div class="krq-scalar"><div class="krq-scalar-l">${esc(label)}</div><div class="krq-scalar-v">${
		esc(value) || "—"
	}</div></div>`;
}

function fmt_age(sec) {
	if (sec == null) return "—";
	if (sec < 60) return `${sec}s ago`;
	if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
	return `${Math.floor(sec / 3600)}h ago`;
}

// Band badge: REVIEW = amber (same hue as the stale badge), PASS = neutral, anything else
// = neutral with the band string shown verbatim (forward-compat for a future FAIL).
function band_badge(band, band_class) {
	if (band == null || band === "") return "";
	return `<span class="krq-badge krq-badge--${esc(band_class || "other")}">${esc(band)}</span>`;
}

// Queue staleness pill — reuses the Phase-2 180s transactions threshold + amber UX.
function queue_pill(data) {
	if (data.never_received) {
		return `<span class="krq-pill krq-pill--neutral">${__("Awaiting first push…")}</span>`;
	}
	if (data.stale) {
		return `<span class="krq-pill krq-pill--stale" title="${__(
			"A single missed push is expected; the next snapshot will clear this.",
		)}">${__("Stale")} (${__("last push")} ${esc(fmt_age(data.age_seconds))})</span>`;
	}
	return `<span class="krq-pill krq-pill--live">${__("Live")} · ${esc(fmt_age(data.age_seconds))}</span>`;
}

function krq_inject_styles() {
	if (document.getElementById("krq-styles")) return;
	const css = `
		.krq-wrap { padding: 8px 4px 24px; }
		.krq-wrap, .krq-wrap * { box-sizing: border-box; }
		.krq-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
		.krq-title { font-size: 16px; font-weight: 600; }
		.krq-sub { color: var(--text-muted); font-size: 12px; margin: 4px 0 14px; }
		.krq-pill { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 20px; white-space: nowrap; }
		.krq-pill--live { color: #1a7f4b; background: rgba(26,127,75,0.10); }
		.krq-pill--stale { color: #9a6700; background: rgba(212,167,44,0.16); }
		.krq-pill--neutral { color: var(--text-muted); background: var(--control-bg, rgba(125,125,125,0.12)); }
		.krq-tablewrap { width: 100%; overflow-x: auto; }
		.krq-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
		.krq-table th, .krq-table td { white-space: nowrap; }
		.krq-table th { text-align: left; color: var(--text-muted); font-weight: 600; padding: 6px 8px;
			border-bottom: 1px solid var(--border-color); }
		.krq-table td { padding: 8px; border-bottom: 1px solid var(--border-color); }
		.krq-row { cursor: pointer; }
		.krq-row:hover { background: var(--control-bg, rgba(125,125,125,0.06)); }
		.krq-num { text-align: right; font-variant-numeric: tabular-nums; }
		.krq-ref { font-weight: 600; }
		.krq-reason { color: var(--text-muted); max-width: 320px; overflow: hidden; text-overflow: ellipsis;
			white-space: nowrap; }
		.krq-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 12px;
			letter-spacing: 0.03em; margin-left: 4px; }
		.krq-badge--review { color: #9a6700; background: rgba(212,167,44,0.16); }
		.krq-badge--pass { color: var(--text-muted); background: var(--control-bg, rgba(125,125,125,0.12)); }
		.krq-badge--other { color: var(--text-muted); background: var(--control-bg, rgba(125,125,125,0.12)); }
		.krq-empty { color: var(--text-muted); font-size: 12.5px; padding: 14px 2px; }
		.krq-back { color: var(--text-muted); font-size: 12.5px; cursor: pointer; margin-bottom: 12px; }
		.krq-back:hover { color: var(--text-color); }
		.krq-detail-card { display: grid; grid-template-columns: 220px 1fr; gap: 18px; align-items: start;
			background: var(--card-bg, var(--fg-color)); border: 1px solid var(--border-color);
			border-radius: var(--border-radius-lg, 10px); padding: 18px; margin-bottom: 18px; }
		@media (max-width: 800px) { .krq-detail-card { grid-template-columns: 1fr; } }
		.krq-score-wrap { text-align: center; }
		.krq-norisk { text-align: left; font-size: 12.5px; color: var(--text-muted); line-height: 1.5; }
		.krq-score { font-size: 40px; font-weight: 800; line-height: 1.1; }
		.krq-score-max { font-size: 16px; font-weight: 500; color: var(--text-muted); }
		.krq-caption { font-size: 11px; color: var(--text-muted); margin-top: 6px; }
		.krq-scalars { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
		.krq-scalar-l { font-size: 10px; color: var(--text-muted); letter-spacing: 0.03em; text-transform: uppercase; }
		.krq-scalar-v { font-size: 13px; }
		.krq-bd-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
		.krq-bd-host { width: 100%; overflow-x: auto; }
		.krq-bd-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
		.krq-bd-table th { text-align: left; color: var(--text-muted); font-weight: 600; padding: 6px 8px;
			border-bottom: 1px solid var(--border-color); }
		.krq-bd-table td { padding: 6px 8px; border-bottom: 1px solid var(--border-color); }
		.krq-bd-row--muted { opacity: 0.45; font-size: 11.5px; }
		.krq-signal { font-family: var(--font-stack-mono, monospace); font-size: 11.5px; }
		.krq-hold { font-size: 12.5px; font-weight: 600; padding: 9px 12px; border-radius: 8px;
			margin: 0 0 14px; border: 1px solid transparent; }
		.krq-hold--prepay { color: #9a6700; background: rgba(212,167,44,0.12); border-color: rgba(212,167,44,0.4); }
		.krq-hold--postpay { color: #8a1f11; background: rgba(193,42,28,0.12); border-color: rgba(193,42,28,0.5); }
		.krq-hold--other, .krq-hold--none { color: var(--text-muted); background: var(--control-bg, rgba(125,125,125,0.10)); }
		.krq-decision { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color); }
		.krq-decision-actions { display: flex; gap: 10px; }
		.krq-decision-actions .btn { min-width: 96px; }
		.krq-reject-form { margin-top: 12px; max-width: 480px; }
		.krq-reject-actions { display: flex; gap: 8px; margin-top: 8px; }
		.krq-decision-result { margin-top: 14px; font-size: 12.5px; font-weight: 600; padding: 10px 12px;
			border-radius: 8px; border: 1px solid transparent; }
		.krq-result-state { font-weight: 500; margin-top: 4px; }
		.krq-result--info { color: #1a7f4b; background: rgba(26,127,75,0.10); border-color: rgba(26,127,75,0.3); }
		.krq-result--warning { color: #9a6700; background: rgba(212,167,44,0.14); border-color: rgba(212,167,44,0.45); }
		.krq-result--error { color: #8a1f11; background: rgba(193,42,28,0.12); border-color: rgba(193,42,28,0.5); }
	`;
	$(`<style id="krq-styles">${css}</style>`).appendTo(document.head);
}

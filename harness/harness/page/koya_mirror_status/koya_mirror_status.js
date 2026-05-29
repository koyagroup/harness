// Koya Mirror Status — read-only staff display for the Phase-2 display mirrors.
//
// Boundary: this page only READS the mirror snapshots via
// harness.koya_harness.api.mirrors.display_state. It NEVER writes, NEVER calls Koya,
// and exposes no approve/reject/edit actions — the mirror is observability only.
//
// Stale UX is INFORMATIONAL, not alarm: a single missed fire-and-forget push is
// expected. Stale shows a muted amber badge next to last-good data — never a blank
// screen, never a flashing alert.

frappe.pages["koya-mirror-status"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Koya Mirror Status"),
		single_column: true,
	});

	inject_styles();

	const $root = $(`
		<div class="kms-wrap">
			<div class="kms-meta">
				<span class="kms-server-now"></span>
				<span class="kms-refreshing">· ${__("refreshing…")}</span>
			</div>
			<div class="kms-cards">
				<div class="kms-card" data-card="rates"></div>
				<div class="kms-card" data-card="txns"></div>
			</div>
		</div>
	`).appendTo(page.body);

	page.set_secondary_action(__("Refresh"), () => load(true), "refresh");

	const POLL_MS = 15000;
	let timer = null;

	function load(manual) {
		$root.find(".kms-refreshing").css("visibility", "visible");
		frappe.call({
			method: "harness.koya_harness.api.mirrors.display_state",
			callback: (r) => {
				if (r && r.message) render(r.message);
			},
			always: () => {
				// Never blank during the network call — just drop the indicator.
				$root.find(".kms-refreshing").css("visibility", "hidden");
			},
		});
	}

	function render(data) {
		$root.find(".kms-server-now").text(`${__("Server time")}: ${data.server_now || "—"}`);
		$root.find('[data-card="rates"]').html(render_rates(data.rates || {}));
		$root.find('[data-card="txns"]').html(render_txns(data.transactions || {}));
	}

	load(true);
	timer = setInterval(() => load(false), POLL_MS);

	// Stop polling when the user navigates away from this page.
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

function status_pill(mirror) {
	if (mirror.never_received) {
		return `<span class="kms-pill kms-pill--neutral">${__("Awaiting first push…")}</span>`;
	}
	if (mirror.stale) {
		return `<span class="kms-pill kms-pill--stale" title="${__(
			"A single missed push is expected; the next snapshot will clear this.",
		)}">${__("Stale")} (${__("last push")} ${esc(fmt_age(mirror.age_seconds))})</span>`;
	}
	return `<span class="kms-pill kms-pill--live">${__("Live")} · ${esc(fmt_age(mirror.age_seconds))}</span>`;
}

function render_rates(m) {
	const rows = (m.rates || [])
		.map((r) => {
			const rate_stale = r.stale
				? `<span class="kms-dot kms-dot--stale" title="${__("Provider reported stale")}"></span>`
				: `<span class="kms-dot kms-dot--ok"></span>`;
			return `<tr>
				<td>${esc(r.pair || r.asset)}</td>
				<td class="kms-num">${esc(r.mid_rate)}</td>
				<td class="kms-num">${esc(r.buy_rate)}</td>
				<td class="kms-num">${esc(r.sell_rate)}</td>
				<td class="kms-num">${esc(r.spread_pct)}</td>
				<td>${esc(r.source)}</td>
				<td>${rate_stale}</td>
			</tr>`;
		})
		.join("");

	const table = rows
		? `<table class="kms-table">
				<thead><tr>
					<th>${__("Pair")}</th><th class="kms-num">${__("Mid")}</th>
					<th class="kms-num">${__("Buy")}</th><th class="kms-num">${__("Sell")}</th>
					<th class="kms-num">${__("Spread %")}</th><th>${__("Source")}</th><th>${__("Stale")}</th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>`
		: `<div class="kms-empty">${__("No rates in the latest snapshot.")}</div>`;

	return `
		<div class="kms-card-head">
			<div class="kms-card-title">${__("Rates")}</div>
			${status_pill(m)}
		</div>
		<div class="kms-card-sub">
			${m.last_source ? `${__("Sources")}: ${esc(m.last_source)} · ` : ""}
			${__("Snapshot")}: ${esc(m.snapshot_at) || "—"}
		</div>
		${table}`;
}

function render_txns(m) {
	const pii = m.pii_warning
		? `<div class="kms-notice">${esc(m.pii_warning)}</div>`
		: "";

	const counts = Object.entries(m.status_counts || {})
		.map(
			([k, v]) =>
				`<div class="kms-count"><div class="kms-count-n">${esc(v)}</div><div class="kms-count-l">${esc(k)}</div></div>`,
		)
		.join("");
	const counts_grid = counts
		? `<div class="kms-counts">${counts}</div>`
		: `<div class="kms-empty">${__("No status counts.")}</div>`;

	const rows = (m.recent || [])
		.map(
			(t) => `<tr>
			<td><span class="kms-ref">${esc(t.ref)}</span></td>
			<td>${esc(t.state)}</td>
			<td>${esc(t.asset)}</td>
			<td class="kms-num">${esc(t.kes_amount)}</td>
			<td class="kms-num">${esc(t.asset_amount)}</td>
			<td class="kms-txid">${t.txid ? esc(t.txid) : "—"}</td>
			<td>${esc(t.updated_at)}</td>
		</tr>`,
		)
		.join("");

	const table = rows
		? `<table class="kms-table">
				<thead><tr>
					<th>${__("Ref")}</th><th>${__("State")}</th><th>${__("Asset")}</th>
					<th class="kms-num">${__("KES")}</th><th class="kms-num">${__("Asset Amt")}</th>
					<th>${__("Tx ID")}</th><th>${__("Updated")}</th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>`
		: `<div class="kms-empty">${__("No recent transactions in the latest snapshot.")}</div>`;

	return `
		<div class="kms-card-head">
			<div class="kms-card-title">${__("Transactions")}</div>
			${status_pill(m)}
		</div>
		<div class="kms-card-sub">${__("Snapshot")}: ${esc(m.snapshot_at) || "—"}</div>
		${pii}
		${counts_grid}
		${table}`;
}

function inject_styles() {
	if (document.getElementById("kms-styles")) return;
	const css = `
		.kms-wrap { padding: 8px 4px 24px; }
		.kms-meta { color: var(--text-muted); font-size: 12px; margin-bottom: 12px; }
		.kms-refreshing { visibility: hidden; margin-left: 6px; }
		.kms-cards { display: grid; grid-template-columns: 1fr; gap: 16px; }
		@media (min-width: 1100px) { .kms-cards { grid-template-columns: 1fr 1fr; } }
		.kms-card { background: var(--card-bg, var(--fg-color)); border: 1px solid var(--border-color);
			border-radius: var(--border-radius-lg, 10px); padding: 16px 18px; }
		.kms-card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
		.kms-card-title { font-size: 16px; font-weight: 600; }
		.kms-card-sub { color: var(--text-muted); font-size: 12px; margin: 4px 0 12px; }
		.kms-pill { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 20px; white-space: nowrap; }
		.kms-pill--live { color: #1a7f4b; background: rgba(26,127,75,0.10); }
		.kms-pill--stale { color: #9a6700; background: rgba(212,167,44,0.16); }
		.kms-pill--neutral { color: var(--text-muted); background: var(--control-bg, rgba(125,125,125,0.12)); }
		.kms-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
		.kms-dot--ok { background: #1a7f4b; opacity: 0.5; }
		.kms-dot--stale { background: #d4a72c; }
		.kms-notice { color: #9a6700; background: rgba(212,167,44,0.14); border: 1px solid rgba(212,167,44,0.4);
			border-radius: 6px; padding: 8px 10px; font-size: 12px; margin-bottom: 12px; }
		.kms-counts { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; margin-bottom: 14px; }
		.kms-count { border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 10px; text-align: center; }
		.kms-count-n { font-size: 18px; font-weight: 700; }
		.kms-count-l { font-size: 10px; color: var(--text-muted); letter-spacing: 0.03em; }
		.kms-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
		.kms-table th { text-align: left; color: var(--text-muted); font-weight: 600; padding: 6px 8px;
			border-bottom: 1px solid var(--border-color); }
		.kms-table td { padding: 6px 8px; border-bottom: 1px solid var(--border-color); }
		.kms-num { text-align: right; font-variant-numeric: tabular-nums; }
		.kms-ref { font-weight: 600; }
		.kms-txid { font-family: var(--font-stack-mono, monospace); font-size: 11px; max-width: 180px;
			overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; vertical-align: bottom; }
		.kms-empty { color: var(--text-muted); font-size: 12.5px; padding: 10px 2px; }
	`;
	$(`<style id="kms-styles">${css}</style>`).appendTo(document.head);
}

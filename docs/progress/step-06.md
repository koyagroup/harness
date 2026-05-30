# Step 06 — App polish: branding, desk presence, and dashboards

**Date:** 2026-05-30
**Branch:** `feat/harness-polish`
**Scope:** HARNESS-POLISH, gates P1–P4. Koya-independent waiting-window work — make `koya_harness`
a polished, desk-installable app: app-launcher identity + branding, dashboards (charts + number
cards) over data we already receive, and clean workspace navigation. **No money path, no settlement
code, no live-fire flag, no contract** touched. Purely presentation + structure, additive on top of
the existing 164 tests.

**Headline:** all four gates done; the existing **164 tests stay green** (116 integration + 48
unit — unchanged). Built from HARNESS-RECON-CRM: CRM is the reference for branding + workspace
idioms only; the chart mechanism comes from **Frappe core** (Dashboard Chart / Number Card /
Dashboard Chart Source), since CRM is a Vue SPA and ships no desk charts.

---

## P1 — App branding + desk presence
**Built:**
- `hooks.py` (mirrors `crm/hooks.py:7-23`): `app_icon_url = "/assets/harness/images/logo.png"`,
  `app_icon_title = "Koya Harness"`, `app_icon_route = "/app/koya-harness-home"` (the desk landing
  page — NOT an SPA route), and `add_to_apps_screen` with
  `has_permission = "harness.api.permission.check_app_permission"`.
- **New** `harness/api/permission.py` `check_app_permission()` — `Administrator` or a harness role
  (System Manager / koya_harness_compliance / koya_harness_ops) → True, else False. Visibility gate
  only; data endpoints/doctypes keep their own server-side perms.
- Assets `harness/public/images/{logo.png,desk.png}` committed (were untracked).

**Verification:** post `clear-cache` + `build`: `app_icon_url`/`app_icon_route` hooks registered;
`add_to_apps_screen` includes `harness`; `check_app_permission()` → True for Administrator, **False
for Guest**; asset resolves at `sites/assets/harness/images/logo.png`.

## P2 — Zero-code dashboards over `Koya Review Item` (normalized → no custom code)
**Built** (is_standard records in module folders, synced on migrate — no fixtures hook):
- **Number Cards** (`Count`): `Items In Review`, `Post-Payment Holds`
  (`hold_reason = btc_delivery_retry_exhausted`), `High-Score Holds` (`risk_score >= 90`).
- **Group By charts**: `Review Queue by Band` (Donut, `risk_band`), `Review Queue by Hold Reason`
  (Bar, `hold_reason`).

**Verification:** all five synced into the DB (module `Harness`). 0 rows → Group By builder returns
`None` → desk renders empty (by design). Transient data (2 REVIEW + 1 PASS, **rolled back**) →
`labels ['REVIEW','PASS']`, `values [[2,1]]` — computes correctly.

## P3 — Custom-source dashboard over the JSON-in-Single mirror data
**Built:**
- **New `Dashboard Chart Source` "Koya Conversion Status Counts"**
  (`harness/harness/dashboard_chart_source/...`): `get` (whitelisted + `@cache_source`, mirroring
  erpnext `account_balance_timeline`) delegates to a decorator-free `_chart()`; parses
  `Koya Transaction Mirror.status_counts_json` → `{labels, datasets}`. Total/forward-compat:
  missing / blank / invalid / non-dict snapshot → empty chart, never raises.
- **New Custom chart "Koya Conversion Status"** (`chart_type:"Custom"`, `source:"Koya Conversion
  Status Counts"`, Bar).

**Verification:** synced; against the live snapshot →
`PAYOUT_DETAILS_PENDING 581, IDENTITY_PENDING 497, PAYMENT_PENDING 200, EXPIRED 174, COMPLETED 138,
MANUAL_REVIEW 87, FAILED 12` (sorted desc). Snapshot nulled (rolled back) → empty, no crash.

## P4 — Workspace + landing page + document
**Built:**
- `koya_harness.json` workspace: `charts[]` (3) + `number_cards[]` (3) populated, plus `content`
  blocks — a **DASHBOARD** section (3 number cards + the 3 charts) above an **OPERATIONS** section
  (the 4 existing shortcuts). Role-gating preserved (System Manager + compliance + ops; NOT public).
- `koya_harness_home.js`: a **Dashboard** section links to the workspace (routes via
  `frappe.set_route("Workspaces","Koya Harness")`) — no chart re-rendering in JS.

**Verification:** workspace in DB has 3 charts + 3 cards + 14 content blocks; every referenced
chart/card exists (no dangling references). `node --check` passes. Full suite **164/164 green**
(unchanged — additive).

---

## Deviations surfaced (none silently worked around)
1. **`get` vs `get_data` (correction to the build instruction).** The Dashboard Chart Source entry
   method is **`get`** (whitelisted, optional `@cache_source`), NOT `get_data` as the instruction
   said. Verified against `frappe/.../dashboard_chart_source` + erpnext's `account_balance_timeline`.
2. **Workspace re-sync needs a bumped `modified`.** `import_file_by_path`
   (`frappe/modules/import_file.py:124-141`) skips re-importing a pre-existing record whose file
   `modified` is not newer than the DB's (it trusts the timestamp/hash). The first migrate did NOT
   update the workspace; bumping the file's `modified` to "now" forced the re-sync. Future workspace
   edits must bump `modified`.
2b. **`stats_filter` count badges** apply to DocType shortcuts only; the harness nav uses custom
   desk Pages, so the in-review count is surfaced via the "Items In Review" Number Card on the
   dashboard rather than a shortcut badge (cleaner).
3. **Zero-count states omitted** from the conversion-status chart for legibility (the flat dict has
   ~15 states, mostly 0). The raw counts remain on the mirror doctype; reversible if all states are
   wanted.
4. **`check_app_permission` is role-based** (Administrator or a harness role), simpler than CRM's
   module-allowed-modules check — sufficient for a visibility gate, matches harness patterns.
5. **logo.png / desk.png are byte-identical placeholders** (33809 b). Committed as-is per the
   instruction (do not generate images); the operator can replace `desk.png` with a distinct icon
   and `logo.png` with the real brand mark later — the wiring is in place.

## What is NOT built (bounded scope)
- No SPA / `frontend/` build / vue-router / frappe-ui / `website_route_rules` / `www/` mount.
- No money-path / settlement / live-fire / contract change.
- No new tests (additive presentation/structure; the existing 164 are the regression gate).

## Carry-over debt (unchanged + additive)
- Re-rotate both secrets pre-mainnet; `developer_mode`/`allow_tests` held; endpoint path text
  reconciliation; `harness_phase4_live_fire` flipped ON only in the coordinated window;
  confirm the hold-reason mirror field name with Koya.
- **NEW:** replace the placeholder `logo.png`/`desk.png` with real, distinct brand assets.

## Next
Phase 4 still awaits Koya's settlement-decision endpoint + a coordinated joint-test window
(live-fire OFF). The harness is now a polished, branded, desk-installable control-plane app.

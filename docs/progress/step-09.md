# Step 09 — Standard-views-first redesign across all surfaces

**Date:** 2026-05-31
**Branch:** `feat/redesign-surfaces`
**Scope:** HARNESS-REDESIGN, gates R1–R5. Shift the harness from "mostly hand-painted custom pages"
toward the mature-Frappe idiom (mostly standard List/Form views + workspace dashboards), surface by
surface. **Presentation only** — NO money-path / live-fire / settlement-send / contract change; the
signed-decision action path is reused unchanged. Grounded in the HARNESS-RECON-HRMS findings (a
mature desk app is ~166 doctypes : 2 custom pages).

**Headline:** all five gates done; **180 tests green** (132 integration + 48 unit) — unchanged, this
is presentation + structure. The reviewer's queue is now a standard List + enriched Form; histories
render via native DataTable / List indicators; the workspace is a real landing.

---

## R1 — Workspace + identity
- Workspace `Koya Harness`: added a **LIVE** section with two **quick-lists** — "Pending Review"
  (`Koya Review Item`) and "Recent Decisions" (`Koya Harness Audit Log`, filtered to
  `settlement_decision_sent`) — above the DASHBOARD (charts+cards) and OPERATIONS (shortcuts).
- **Deviation:** did NOT set `app_home` — it's a *global* hook that would hijack the default home
  for ALL users on this shared erpnext/hrms/harness bench. Our per-app landing is already correct
  via `add_to_apps_screen` route → `/app/koya-harness-home` (polish step).

## R2 — Review queue → standard List + enriched Form (the big shift)
- `Koya Review Item`: `in_list_view` on ref/hold_reason/asset/kes_amount/risk_score/risk_band/
  received_at; added read-only HTML host fields (`hold_reason_html`, `risk_breakdown_html`).
- `koya_review_item_list.js`: `get_indicator` colors rows by hold type (delivery=red "PAYMENT IN",
  risk=orange, compliance=blue) — on the free standard list (click→form, sort, filter, scroll).
- `koya_review_item.js` (form script): on refresh calls the existing `review_item_detail` → renders
  the hold-reason banner + risk breakdown (only when `has_risk`, else the no-risk note); when
  `can_decide`, adds **Approve/Reject `frm.add_custom_button`s** → `send_settlement_decision`, with a
  **`frappe.ui.Dialog`** for the reject reason + the server-supplied reason-aware confirmation.
- Nav repointed (workspace shortcut + console link) to the `Koya Review Item` List; the custom
  **`koya-review-queue` page removed** (orphan Page deleted on migrate).
- The money path is reused unchanged — server gate `_require_decision_role` stays authoritative;
  the buttons are defense-in-depth (`can_decide`). `review.py` (`review_item_detail`,
  `review_queue_state`) unchanged, now consumed by the form script + the console count.

## R3 — Decision history DataTable + raw audit List
- `koya_decision_history.js`: hand-painted table → **`frappe.DataTable`** (native sort/scroll/resize;
  badge HTML pre-rendered + escaped). The `decision_history` API, filters, and "System events →"
  link are unchanged. The paired sent↔response view stays custom (the pairing is bespoke).
- `Koya Harness Audit Log`: `correlation_id`+`error_code` added to the list; new
  `koya_harness_audit_log_list.js` `get_indicator` on `outcome` — the raw browse (and the "System
  events" target) is now native + indicator-colored.

## R4 — Mirror dashboards (verified + kept)
The workspace dashboard surface (custom-source `Koya Conversion Status` chart over the mirror
`status_counts_json`, + the review Group-By charts + number cards) was completed in the polish step
and is intact. `koya-mirror-status` is kept as the **bespoke live-stale surface** (the real-time
stale-badge UX a doctype view can't express). **Skipped** the optional named `Dashboard` record
(redundant with the workspace's embedded charts/cards) and a rate-freshness card (shown live on
mirror-status; marginal). No new code — a conscious anti-redundancy call.

## R5 — Document + commit (this step).

---

## The redesign in one line
Moved the two record-shaped surfaces (review queue, raw audit log) onto **standard List/Form views**
(free click/sort/filter/scroll/badges), kept **custom only** where the affordance is genuinely
bespoke — the signed-decision buttons (as native form buttons), the paired decision history (native
DataTable), the per-section-gated console landing, and the live mirror stale UX. That is the
HRMS-idiomatic balance.

## Deviations / decisions surfaced
1. `app_home` skipped (global hook; would hijack the shared bench) — per-app landing via the
   apps-screen route already correct.
2. Removed `koya-review-queue` custom page (replaced by List+Form); `review_item_detail` /
   `review_queue_state` kept (reused).
3. HRMS uses neither the Workflow engine nor approve/reject buttons (a permlevel status + submit) —
   that doesn't fit our *action* (a signed POST to Koya), so custom form buttons are the right,
   idiomatic host for a bespoke action (matching how HRMS hosts *secondary* actions).
4. Skipped the redundant named Dashboard record + rate card (R4) with rationale.
5. The JS surfaces (list/form scripts, DataTable) have no automated test on this bench — verified by
   syntax + the unchanged 180-test suite (the action/render APIs are unchanged + already tested);
   visual confirmation is a manual desk walk-through.

## What is NOT changed
No money-path / live-fire / settlement-send / contract change. Live-fire OFF. No HRMS Vue/SPA
patterns (desk only). No raw reason/amount/PII surfaced anywhere.

## Next
Harness redesigned to the standard-views-first idiom. Live-fire OFF. The delivery-hold joint test
remains pending Koya's P0 fix + a coordinated window.

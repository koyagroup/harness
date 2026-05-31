# Step 10 — Restore the custom review-queue page (operator preference)

**Date:** 2026-05-31
**Branch:** `feat/redesign-surfaces`

The step-09 redesign converted the review queue to a standard `Koya Review Item` List + enriched
Form (the approved fork). On review, the operator preferred the **previous custom
`koya-review-queue` page** (route-driven list↔detail with the risk breakdown, hold-reason banner,
and Approve/Reject affordance). This step **reverts the R2 review-queue change only** — the rest of
the redesign stays.

## Reverted (R2 only)
- Restored `harness/harness/page/koya_review_queue/` (`__init__.py`, `.js`, `.json`) from the
  pre-redesign state (`feat/audit-view`) — the cleaned-up (scroll-wrapped) custom page with its
  decision affordance, all reusing the unchanged `review_item_detail` / `review_queue_state` /
  `send_settlement_decision` / `decision_render` paths.
- Restored `koya_review_item.json` to its pre-R2 state (kept `has_risk`/`hold_reason` from the
  filter-fix; dropped the R2-only `in_list_view` additions + the `hold_reason_html`/
  `risk_breakdown_html` HTML host fields).
- Removed the R2 doctype scripts `koya_review_item.js` (form) + `koya_review_item_list.js` (list).
- Repointed nav back to the page: the workspace "Review Queue" shortcut → Page `koya-review-queue`;
  the console landing link → `koya-review-queue`.

## Retained (NOT reverted)
- **R1** workspace LIVE quick-lists (Pending Review, Recent Decisions) + the dashboards.
- **R3** decision-history `frappe.DataTable` + the raw `Koya Harness Audit Log` List indicators.
- **R4** workspace dashboards + the live mirror-status surface.

## Verification
`bench migrate` re-syncs the page + drops the R2 HTML fields (no data loss — HTML fields have no DB
column); workspace re-synced (quick-lists intact). Full suite **180/180** (the action/render APIs
were never touched). The custom review-queue page works exactly as before the redesign.

## Net
Review queue = the custom page (operator's choice); decision history + workspace keep the redesign
polish. Money path unchanged; live-fire OFF.

# Step 08 — Reviewer-facing decision history (compliance audit trail)

**Date:** 2026-05-31
**Branch:** `feat/audit-view`
**Scope:** HARNESS-AUDIT-VIEW, gates G1–G4. A read-only compliance VIEW over the append-only audit
data Phase 4 already captures — what was approved/rejected, by whom, when, the hold reason, and the
`resulting_state` Koya returned. **No Koya dependency, no money-path / live-fire / settlement /
contract change.** Additive.

**Headline:** all gates done; **180 tests green** (132 integration + 48 unit), up from 171 (+9 in
`test_audit_view`). The decision trail is now reachable by reviewers; system (mirror/health) events
stay separate.

---

## G1 — `decision_history` read API
**New `koya_harness/api/audit_view.py`** `decision_history(filters=None, limit=100)`:
- **Gate first** (`can_send_decisions()` = compliance OR System Manager); ops → `permitted:False`.
  Decision history is compliance data — NOT gated on `has_permission(audit, read)` (which would let
  ops in).
- Queries `Koya Harness Audit Log` for `event_type IN (settlement_decision_sent,
  settlement_decision_response)` (decision events only — system events excluded), newest first, a
  generous window so pairs aren't split.
- **Pairs sent↔response by `harness_request_id`** into one record `{session_ref, request_id,
  decision, reviewer, decided_at, hold_reason, hold_reason_label, resulting_state, resulting_label,
  idempotent, outcome, error_code, response_time, status}`. Status: `responded` / `pending`
  (sent, no response — shown, not hidden) / `orphan_response` (anomaly, surfaced).
- Optional filters: decision / hold_reason / outcome / reviewer / from_date / to_date.
- `detail_json` parsed defensively (`json.loads` in try/except → `{}`; `.get` every key).

**Deviation (correctness, flagged):** the instruction said "pair by correlation_id (session_ref)",
but a `session_ref` can have multiple decision attempts (retry / re-decide). Pairing by
`harness_request_id` (unique per attempt) is correct; `session_ref` is the display/group key. The
test `test_multiple_attempts_same_session_paired_separately` proves two attempts on one session_ref
produce two distinct records.

**Verification:** `tests/test_audit_view.py` **9/9** — pair → one `responded` record; sent-only →
`pending`; multiple attempts on one session → separate records; system events excluded; ops →
`permitted:False`, compliance/SM → data; missing `detail_json` keys → no crash; **output carries no
raw reason text / amount / PII** (a reason containing "structuring near 95000" is never in the
output — it was never stored); decision filter narrows correctly.

## G2 — Decision-history desk page
**New Page `koya-decision-history`** (`roles: [System Manager, koya_harness_compliance]` — NOT ops):
a read-only table, newest first — Session · Decision (APPROVE/REJECT badge) · Hold reason · Reviewer
· Decided · Resulting state · Outcome (success/warning/failure badge) · Idempotent. Visual cues:
APPROVE vs REJECT distinct; **REFUND_PENDING styled distinctly** (refund obligation); failure
outcomes flagged; `pending` rows muted. Simple filter controls (decision / outcome / hold_reason /
date range). Scroll-wrapped table + box-sizing (the step-06b UI convention). No actions.

## G3 — System events: reachable, separate
The page has a **"System events →"** link that routes to the `Koya Harness Audit Log` list view
filtered (`frappe.route_options`) to the system event types (`mirror_rates_received`,
`mirror_transactions_received`, `mirror_risk_validation_warning`, `health_ping_received`). The
decision trail stays decision-only; ops can still read system events via that list (they have read on
the audit doctype). No second custom page — lowest-code clean separation.

## G4 — Wired in + documented
- Workspace `Koya Harness`: added a "Decision History" shortcut + content block under OPERATIONS;
  bumped `modified` so `import_file` re-syncs (the step-06 gotcha).
- Landing page `koya-harness-home`: a compliance-gated "Decision History" link (the `is_compliance`
  branch) routing to `koya-decision-history`.

**Verification:** Page synced; workspace shortcut present; full suite **180/180** (additive — the 171
unchanged).

## Deviations surfaced
1. **Pair by `harness_request_id`, not `correlation_id`** (correctness for multi-attempt sessions) —
   see G1.
2. The page is gated to compliance + SM (NOT ops) at both the Page-roles level and the API gate; ops
   reach system events via the audit list, not the decision trail.

## What is NOT built
Surfacing/recovering raw reason text (value-free by design; a future feature with its own privacy
review); any settlement/decision-send/live-fire change.

## Next
Decision-history view live. Live-fire OFF. Delivery-hold joint test still pending Koya's P0 fix + a
coordinated window.

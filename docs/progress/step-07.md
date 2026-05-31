# Step 07 — Surface all three MANUAL_REVIEW hold types in the review queue

**Date:** 2026-05-30
**Branch:** `feat/filter-fix-all-holds`
**Scope:** HARNESS-FILTER-FIX, gates G1–G5. Relax the review-queue reconcile filter so all three
v3 hold types surface (risk / compliance / delivery), render no-risk holds honestly (banner + note,
no misleading 0-score, no empty breakdown), and VERIFY the Phase-4 reason-aware decision surface
fires for the delivery case. **No money-path / live-fire / settlement / contract change.** Additive.

**Headline:** all gates done; **171 tests green** (123 integration + 48 unit), up from 164 (+7 in
`test_all_hold_types`). The delivery-hold (post-payment, refund-bearing) decision is now reachable —
the delivery-hold joint test is unblocked on the harness side.

**Why:** the pre-keystone recon found the live v3 mirror carries three hold types, but our reconcile
only queued items with a `risk` object (`mirrors.py:215`). Compliance- and delivery-holds carry
`hold_reason` but no `risk` object (held by the compliance screen / delivery exhaustion, not the
scorer) → they never reached the queue → the heaviest decision (delivery REJECT = refund) was
invisible and untestable.

---

## G1 — Relaxed filter + honest "no risk" representation
- `_reconcile_review_items` (`koya_harness/api/mirrors.py`): filter is now
  `state == "MANUAL_REVIEW" AND ("risk" in item OR "hold_reason" in item)` (neither → still skipped).
- **New `has_risk` (Check, read-only) field** on `Koya Review Item` (additive, synced on migrate),
  set `doc.has_risk = 1 if risk else 0` (`risk` is `{}` for a no-risk hold → 0).
- **The misleading-0 problem (flagged):** `_coerce_int(None) → None`, and `None` into the
  non-nullable Int `risk_score` stores as **0**. So "no score" can't live in `risk_score`. `has_risk`
  is the single source of truth — the stored 0 for a no-risk hold is **inert** (never rendered; the
  read APIs gate the score/breakdown on `has_risk`).

## G2 — Render: banner always, breakdown only when risk present
- `review_queue_state` (`review.py`): selects `has_risk`; returns `score = risk_score if has_risk
  else None` (the page already renders `null → "—"`).
- `review_item_detail`: returns `has_risk` + `no_risk_note`; the risk surface
  (score/band/scorer/computed/`breakdown_html`) is populated **only when `has_risk`**, else
  score=None, `breakdown_html=""` (NOT the placeholder table), and a reason-specific `no_risk_note`.
- **New pure helper `decision_render.no_risk_note(hold_reason)`** — e.g. compliance → "Held by the
  compliance screen — not risk-scored"; delivery → "Held after BTC delivery retries were exhausted —
  PAYMENT RECEIVED; not risk-scored".
- Page `koya_review_queue.js` `paint_detail`: the hold-reason banner renders for all types; when
  `!has_risk` the score block is replaced by the `no_risk_note` and the breakdown section is omitted.

## G3 — Reason-aware decision surface: VERIFIED, no change needed
`decision_render.confirmation_text` (built + unit-tested in Phase 4 G4.2) correctly handles all four
(hold_reason × decision) cases:
- delivery (`btc_delivery_retry_exhausted`) **REJECT → "book a REFUND OBLIGATION — the customer's KES
  is owed back"**; **APPROVE → "RETRY BTC delivery? KES has already been collected"**;
- risk/compliance APPROVE → "resume"; REJECT → "decline … no funds were collected".
`review_item_detail` returns `confirm_approve`/`confirm_reject`/`can_decide`; `can_decide =
can_send_decisions()` is hold-type independent → true for compliance/SM on all three. **Verified,
fires correctly, no code change.**

## G4 — Test
`tests/test_all_hold_types.py` (**7/7**): a v3 push of risk + compliance + delivery + COMPLETED →
exactly the 3 holds queue (COMPLETED excluded); `has_risk` 1/0/0; the two no-risk holds return
`score=None` (not 0) + `breakdown_html=""` + a `no_risk_note`; the risk hold has a breakdown; banners
correct (delivery class `postpay`, "PAYMENT RECEIVED"); confirmations per type (delivery REJECT =
REFUND wording); `can_decide` true for all three for a compliance user.

**Regression:** the full suite stays green — **171/171** (123 integration + 48 unit). Notably
`test_manual_review_without_risk_not_queued` stays green: its item has neither `risk` nor
`hold_reason`, so it's still not queued under the relaxed filter (verified before the change).

## Deviations surfaced
1. **`has_risk` field added** to represent "no score" honestly (a non-nullable Int can't be null);
   the inert stored 0 for no-risk holds is never rendered.
2. **G3 was a verification, not a rebuild** — the delivery-reject refund wording was already correct
   (Phase 4); no fix required.
3. The live web tier still runs pre-filter-fix code (last reloaded during the keystone disarm); the
   live compliance-holds will surface once this branch is deployed and the web tier reloads. The
   `test_all_hold_types` suite is the authoritative proof until then.

## What is NOT built
Settlement/decision-send change; live-fire (stays OFF); the actual delivery-hold joint test (gated on
Koya's P0 fix + a coordinated window).

## Next
Delivery-hold joint test is unblocked on the harness side — awaiting Koya's P0 fix + a coordinated
window. Live-fire OFF.

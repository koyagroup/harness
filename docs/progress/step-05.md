# Step 05 — Phase 4 harness half: settlement decision (reviewer approve/reject)

**Date:** 2026-05-30
**Branch:** `feat/p4-settlement-decision`
**Scope:** HARNESS-P4, gates G1–G7. The money-moving direction, built against the FROZEN
Phase-4 contract and MOCKED Koya responses. The real POST is behind a build-time flag
(`harness_phase4_live_fire`, default OFF). No live integration against Koya; no contract
edits; no `developer_mode`/`allow_tests` change.

**Headline:** all six build gates done; **164 tests green** (116 integration + 48 unit), up
from Phase-3's 112. Live-fire ships **OFF**. Awaiting Koya's settlement-decision endpoint
deploy + a coordinated joint-test window.

**Boundary check:** the harness expresses INTENT (a signed decision keyed to a `session_ref`);
Koya executes against its own locked record and derives amount/destination itself. The
request body carries NO amount, NO destination, NO asset, NO payout instruction
(injection-defense). Still no key material beyond the inbound HMAC secret; no wallet/BitGo/AWS
contact; signing reuses the one signer (`client.post_signed`).

---

## G1 — server-side compliance action gate (the recon-Q3 build-item)
**Built** (`koya_harness/api/settlement.py`): `_require_decision_role()` (+ public
`can_send_decisions()`) — `koya_harness_compliance` OR `System Manager` via
`frappe.get_roles()`, raising `frappe.PermissionError` as the FIRST line of
`send_settlement_decision`, before any body is built or any transport attempted. This is the
money-path action gate; it did not exist before (recon Q3: the prior `has_permission` gate in
`review.py` gates READ only). Scope (compliance OR System Manager) was an operator decision.

**Verification:** `tests/test_decision_gate.py` **4/4** — no-role → PermissionError + no POST;
`koya_harness_ops` → blocked; `koya_harness_compliance` → passes; `System Manager` → passes.

## G2 — inbound-signed decision request
**Built:** `send_settlement_decision(session_ref, decision, reason=None)` — gate → validate →
build → send/simulate → handle → audit. The STABLE body is contract-exact and money-free:
`request_id` (uuid4 lowercase), `session_ref`, `decision`, `reviewer` (`frappe.session.user`,
audit-only), `decided_at` (RFC3339 ms UTC), `reason` (REJECT only). REJECT without a reason
or an invalid decision → structural `validation_error`, never sent. Signs via `post_signed`
(inbound secret); path `/internal/harness/settlement-decision`. Live-fire seam: flag OFF
(default) → a simulated Koya-shaped response, no real POST; flag ON → `post_signed(...,
with_status=True)`.

**Verification:** `tests/test_settlement_send.py` **8/8** (body shape; NO amount/destination/
asset; reason rules; live-fire on/off) + `tests/test_client.py` **10/10** (the 6 prior tests
unchanged + 4 new guarding the `with_status` opt-in and the bare-dict default).

## G3 — response handling (fire-with-confirmation)
**Built:** `_handle_response(body, http_status)` → UI reflection. 200-accepted reflects
`resulting_state`; 200-idempotent says "already processed" (no double-submit, no error);
409 shows the actual current state as a WARNING (not a hard error); 404/400/401/403 surfaced
honestly (401 logged prominently); transport / status-None → "may not have landed", never
"landed". `decision_render.resulting_state_label` renders the state as a STRING —
REFUND_PENDING reads differently from REJECTED; an unknown sixth state renders generically.

**Verification:** `tests/test_settlement_response.py` **14/14**.

## G4 — reviewer approve/reject UI
**Built:**
- DocType `Koya Review Item` gained an additive `hold_reason` (Data, read-only) field.
- `_reconcile_review_items` captures `item.get("hold_reason")` (forward-compat; absent → None).
- `review_item_detail` returns `hold_reason` + `hold_reason_label`/`hold_reason_class` +
  `can_decide` + `confirm_approve`/`confirm_reject` — all from the pure `decision_render`
  module so the (hold_reason × decision) matrix and banner copy are single-sourced.
- Page `koya-review-queue` (`paint_detail`): hold-reason banner (post-payment styled distinct,
  "PAYMENT RECEIVED"); Approve/Reject buttons drawn only when `can_decide`; Reject reveals a
  required-reason input; both pass through a reason-aware confirmation whose text the SERVER
  supplies; result reflected with severity styling; on success the actions hide (the item
  leaves on the next snapshot — Koya's skip-flag).

**Verification:** `tests/test_review_decision_ui.py` **14/14** (the 4 confirmation cases — the
post-payment REJECT reads as a REFUND OBLIGATION; banner labels/classes; detail returns
hold_reason + can_decide for compliance, ops cannot read it; server-side reject-reason
validation; reconcile captures hold_reason) + `tests/test_review_queue.py` **11/11** (no
regression). `node --check` passes on the page JS.

## G5 — audit decision + response
**Built:** a money-path `_audit()` wrapper (best-effort + prominent error log) writes
`settlement_decision_sent` (detail = decision/reviewer/`reason_present`/`reason_len`/
hold_reason — value-free) and `settlement_decision_response` (resulting_state/idempotent/
outcome/error_code). No audit-doctype schema change (recon Q2).

**Verification:** `tests/test_settlement_audit.py` **4/4** — both rows written + correlated; a
reason containing `95000`/`btc1qxyz` leaks NEITHER the text nor any amount/destination token;
a 404 → `failure` + `not_found`; a forced `write_audit` failure does not break the decision.

## G6 — live-fire flag discipline + safety
**Built/verified:** the two controls are independent — flag OFF (default) → no real POST under
approve/reject/retry; flag ON does NOT bypass the G1 gate; flag ON + compliance → the real
POST path runs (mocked).

**Verification:** `tests/test_live_fire_gate.py` **4/4**.

---

## Test counts
- **Unit / unspecified (48):** prior 30 + **test_settlement_response 14** + **test_client +4**.
- **Integration (116):** prior 82 + **test_decision_gate 4** + **test_settlement_send 8** +
  **test_review_decision_ui 14** + **test_settlement_audit 4** + **test_live_fire_gate 4**.
- **Total 164**, all green (Phase 3 was 112). Run:
  `bench --site kronos.koyabank.com run-tests --app harness`.

## Deviations surfaced (none silently worked around)
1. **`post_signed` discarded the HTTP status** (returned only `resp.json()`), and
   `test_client.py` asserts exact dict equality on its return. G3's response-class handling
   needs the status. Added an **opt-in `with_status=False`** param: default behavior + every
   existing caller/test unchanged; `True` → `(body, http_status)` (status None for a transport
   failure). Reuses the one signer — not a second signer.
2. **`hold_reason` mirror field name not yet frozen by Koya.** The contract notes Koya adds a
   hold-reason field to the mirror payload additively, exact name TBD at endpoint sign-off.
   Captured by the expected key `hold_reason`, tolerant of absence; flagged in code +
   `_reconcile_review_items`. **Needs Koya confirmation before the joint test.**
3. **No JS unit runner on this bench.** As in Phase 3, the page JS affordances (button
   rendering, confirm dialog, reason input) are verified by `node --check` + a manual
   compliance-vs-ops login walk-through. The decision LOGIC the JS renders is in the pure
   `decision_render` module and is fully Python-unit-tested (no JS↔Python drift).
4. **Send-gate scope = compliance OR System Manager** (operator decision). System Manager /
   Administrator can send so the operator can test; the money authority is still gated, not
   open. Strictly-compliance-only is a one-line change if wanted later.
5. **`except A, B:` without parens is valid here.** The bench runs Python 3.14 (PEP 758,
   parentheses optional in `except`). New multi-type excepts match the house no-paren idiom.
   (An earlier recon mislabeled this a "display artifact" — corrected: it is PEP 758.)

## What is NOT built (bounded scope)
- **The real joint test against Koya** — gated; needs Koya's endpoint deployed + the flag
  flipped ON in a coordinated window + egress allowlisted.
- **Refund UI / refund execution** — a later phase (REFUND_PENDING is rendered + audited only).
- **Re-hold handling** — trust Koya's skip-flag; an approved item leaves the queue and stays gone.
- No `developer_mode` / `allow_tests` change; no contract path-string edit.

## Carry-over debt
- Re-rotate both secrets pre-mainnet (chat-exposed in earlier steps).
- `developer_mode=1` + `allow_tests=true` intentionally held per Koya's guidance.
- Endpoint path text vs contract §2.1/§3.1 — reconcile on sign-off.
- **NEW: `harness_phase4_live_fire` must be flipped ON only inside the coordinated joint-test
  window, and OFF again after, until production go-live.**
- **NEW: confirm the hold-reason mirror field name with Koya before the joint test.**

## Next
Await Koya's `POST /internal/harness/settlement-decision` deploy. Then, in a coordinated
window: confirm the hold-reason field name, flip `harness_phase4_live_fire` ON, run the
approve/reject round-trip (200-accepted resulting_state, idempotent double-click, 409), verify
the audit pair, flip the flag OFF.

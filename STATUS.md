# Harness — STATUS

> Single source of truth for the harness app's current state. Mirrors the Koya-side
> STATUS so the two builds stay reconcilable. No secret values here — key names only.

**Last updated:** 2026-05-30 (step-05)

## Current phase
**Phase 4 HARNESS HALF complete — live-fire OFF — awaiting Koya's settlement-decision endpoint
deploy + a coordinated joint-test window.** Built against the frozen Phase-4 contract and
MOCKED Koya responses (gates G1–G6): a server-side compliance action gate (compliance OR
System Manager) on the decision-send method; `send_settlement_decision` signs a contract-exact,
money-free body (NO amount/destination/asset) and POSTs via the existing `post_signed` (inbound
secret); full response-class handling (200 accepted/idempotent, 409, 404/400/401/403, transport)
that renders Koya's `resulting_state` as a string (REFUND_PENDING reads differently from
REJECTED); an approve/reject affordance on the Phase-3 review detail with a hold-reason banner
and a reason-aware confirmation (the post-payment reject reads as a REFUND OBLIGATION); and a
decision/response audit pair carrying decision metadata only. The real POST is behind
`harness_phase4_live_fire` (default/absent = OFF). Full suite **164/164** (116 integration + 48
unit). Nothing live against Koya yet. See `docs/progress/step-05.md`.

Phase 3 remains DONE (v2 receiver + review console + audit + roles + landing + health ping,
step-04). Phase 2 remains DONE and proven (§6 kill-switch joint test passed, step-03).

## Wire / secrets state
- Contract: v1 (inbound, LAW) + v1.1 Phase 2 addendum (display mirrors), now checked in
  at `cto/HARNESS_WIRE_CONTRACT_v1.1_phase2.md` (status **PROPOSED**, pending sign-off).
- HMAC scheme unchanged: `HMAC-SHA256(secret, ts + "." + nonce + "." + rawBody)`,
  lowercase 64-hex; headers `X-Harness-Timestamp` / `X-Harness-Nonce` /
  `X-Harness-Signature`. Appendix-A vector verified (`f069372a…c8d996`) — and the
  verifier now *accepts* that vector (the Phase-2 gate).
- `site_config.json` secret keys:
  - `harness_inbound_secret` — H→K signing (ping/settlement/user-control). **Active.**
  - `harness_outbound_secret` — K→H mirror verification. **Active** (verifier built).
  - `harness_shared_secret` — **removed.**
- Code accessors: `get_inbound_secret()` + `get_outbound_secret()`
  (`koya_harness/config.py`).
- **Feature flag (NOT a secret):** `harness_phase4_live_fire` — gates the real settlement
  decision POST. Default/absent = **OFF** (a simulated Koya response is used instead). Flip ON
  only inside a coordinated joint-test window; OFF again after. Independent of the compliance
  gate — BOTH must hold for a real decision to leave the box.

## Receive endpoints (the URLs Koya must POST to)
- `POST /api/method/harness.koya_harness.api.mirrors.rates`
- `POST /api/method/harness.koya_harness.api.mirrors.transactions`
- `POST /api/method/harness.koya_harness.api.health.ping` (Phase 3 — inbound health ping,
  same HMAC verifier + nonce keyspace; not wired into any flow yet).

## Outbound calls (the URLs the harness POSTs to Koya)
- `POST /internal/harness/settlement-decision` (Phase 4 — signed with `harness_inbound_secret`
  via `post_signed`; sent by the whitelisted, compliance-gated
  `harness.koya_harness.api.settlement.send_settlement_decision`). Body is contract-exact and
  money-free. Behind `harness_phase4_live_fire` (OFF by default — simulated until the window).
- (NB: differs from contract §2.1/§3.1 path strings — see step-02 D1, needs sign-off.
  Frappe binds whitelist methods by *installed-app*-prefixed module path; `koya_harness`
  alone is not an app, so the path is app-prefixed `harness.koya_harness.…`.)
- Nonce replay store: Frappe-cache Redis, keyspace `harness:outbound-nonce:`, `SET NX
  EX 600` (distinct from any Phase-1 keyspace).

## Last joint tests
- 2026-05-29 (Phase 1) — four-outcome inbound test on the rotated secret: **4/4 PASS**.
  See `docs/progress/step-01.md`.
- 2026-05-29 (Phase 2 build) — harness-side proofs: verifier 15/15, endpoints 9/9, full
  app 36/36; live signed HTTP round-trip 200/401/401/401 + 400s; PII warn-and-store;
  snapshot overwrite. See `step-02.md`.
- 2026-05-29 (Phase 2 §6 joint test) — **PASSED.** Kill-switch: harness dark 14:57:54Z →
  15:01:50Z; Koya unaffected (quote refreshed mid-outage); mirrors auto-resumed within
  cadence on restore. See `step-03.md`.
- 2026-05-30 (Phase 3 parallel build) — harness-side proofs only: v2 schema 23/23, review
  render 18/18 + queue 11/11, audit 7/7, roles 7/7, landing 4/4, health 6/6; full app
  **112/112**; live HTTP unsigned health ping → §6 `missing_required_headers`. The v2 mirror
  + signed health-ping joint test (gates 5.2.5–5.2.7) awaits Koya's deploy. See `step-04.md`.
- 2026-05-30 (Phase 4 build) — harness-side proofs only (live-fire OFF, all mocked): decision
  gate 4/4, settlement send 8/8 + client 10/10, response handling 14/14, review-decision UI
  14/14, audit 4/4, live-fire gate 4/4; full app **164/164**. The signed approve/reject
  round-trip is the joint-test gate, staged not run (needs Koya's endpoint + the flag ON in a
  coordinated window). See `step-05.md`.

## What exists in the app
- Outbound signer (Phase 1): `koya_harness/{sign,headers,client}.py`.
- Inbound mirror verifier (Phase 2): `koya_harness/{verify,config,pii,log}.py`.
- Endpoints: `api/ping.py`, `api/joint_test.py` (Phase 1);
  `koya_harness/api/mirrors.py` (rates/transactions/display_state) +
  `koya_harness/api/joint_test_p2.py` (run_mirror_smoke) (Phase 2);
  `koya_harness/api/{review,health}.py` + shared `api/_responses.py` (Phase 3);
  `koya_harness/api/settlement.py` (`send_settlement_decision` — outbound, compliance-gated)
  (Phase 4).
- Phase-3 logic: `koya_harness/risk_render.py` (pure render helpers),
  `koya_harness/audit.py` (best-effort audit writer); v2 risk validation + review-queue
  reconciliation added to `koya_harness/api/mirrors.py`.
- Phase-4 logic: `koya_harness/decision_render.py` (pure resulting_state / hold-reason /
  confirmation helpers); compliance action gate + decision send/response + audit in
  `koya_harness/api/settlement.py`; `client.post_signed` gained an opt-in `with_status`
  return; `Koya Review Item` gained a `hold_reason` field; the review-queue detail page gained
  the approve/reject affordance (compliance-gated, reason-aware confirmation).
- Doctypes (Single, read-only): `Koya Rate Mirror`, `Koya Transaction Mirror`.
- Doctypes (Phase 3, read-only): `Koya Review Item` (per-MANUAL_REVIEW row, snapshot-rebuilt),
  `Koya Harness Audit Log` (append-only, no write/delete perms, `on_trash` blocked).
- Roles (Phase 3): `koya_harness_compliance` (reads Review Item + audit + mirrors),
  `koya_harness_ops` (reads audit + mirrors, NOT Review Item). Operator assigns users later.
- Display: desk Pages `koya-mirror-status` (Phase 2), `koya-review-queue` (Phase 3 review
  console, list + detail), `koya-harness-home` (Phase 3 Operations Console landing); Workspace
  `Koya Harness` for discoverability. All read-only, role-gated, informational stale.
- Tests: `tests/test_{sign,headers,client,risk_render,settlement_response}.py` (48 unit) +
  `tests/test_{verify,mirrors,v2_schema,review_queue,audit_log,roles,landing,health,
  decision_gate,settlement_send,review_decision_ui,settlement_audit,live_fire_gate}.py`
  (116 integration) — **164/164 green**.

## Open items / flags
- **Endpoint path text reconciliation** — contract §2.1/§3.1 path strings vs the reachable
  whitelist URLs (step-02 D1). Resolved *in practice* (Koya pushes 200 to
  `/api/method/harness.koya_harness.api.mirrors.*`); contract text wants a matching edit on
  sign-off.
- Re-rotate both secrets before mainnet if this session's transcripts are retained
  (values were pasted in-session — see step-01 D3).
- `allow_tests=true` + `developer_mode=1` set on the site (step-02 D4) — operator may
  disable `allow_tests`.
- Stale-badge gate (§6.2) was not separately exercised as its own pause; the kill-switch
  window covered the stale→fresh transition implicitly (mirrors went stale during the
  outage and un-staled on resume). A dedicated stale-only pause can be run any time via the
  same lever if Koya wants it logged distinctly.
- **Phase 4 live-fire flag** — `harness_phase4_live_fire` flipped ON only inside a coordinated
  joint-test window, OFF again after, until production go-live.
- **Hold-reason mirror field name** — confirm the exact key Koya adds to the v2 mirror item
  before the joint test (captured as `hold_reason`, tolerant of absence; step-05 D2).

## Next
Phase 4 harness half is done (live-fire OFF). Awaiting Koya's `POST
/internal/harness/settlement-decision` deploy. Then, in a coordinated window: confirm the
hold-reason field name, flip `harness_phase4_live_fire` ON, run the signed approve/reject
round-trip (200-accepted `resulting_state`, idempotent double-click, 409 conflict), verify the
decision/response audit pair, flip the flag OFF. (Phase-3's v2-mirror + signed health-ping
joint test, gates 5.2.5–5.2.7, also still awaits Koya's Phase-3 deploy.)

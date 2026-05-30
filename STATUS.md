# Harness — STATUS

> Single source of truth for the harness app's current state. Mirrors the Koya-side
> STATUS so the two builds stay reconcilable. No secret values here — key names only.

**Last updated:** 2026-05-30 (step-04)

## Current phase
**Phase 3 PARALLEL BUILD complete on the harness side — awaiting Koya's Phase-3 deploy for
the joint test.** Built during Koya's deploy window (gates G1–G6): the transactions receiver
now tolerates the v2 `risk` schema (field-presence keyed, warn-and-store), a read-only
review-queue console renders score + band + full breakdown, an append-only audit log records
every receive, two staff roles exist with the right boundaries, a role-gated Operations
Console landing page ties it together, and an inbound health-ping receiver mirrors Phase 1.
Full suite **112/112** (82 integration + 30 unit). Nothing live against Koya yet — the v2
mirror round-trip + signed health ping are the joint-test gates (5.2.5–5.2.7). See
`docs/progress/step-04.md`.

Phase 2 remains DONE and proven (§6 kill-switch joint test passed, step-03).

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

## Receive endpoints (the URLs Koya must POST to)
- `POST /api/method/harness.koya_harness.api.mirrors.rates`
- `POST /api/method/harness.koya_harness.api.mirrors.transactions`
- `POST /api/method/harness.koya_harness.api.health.ping` (Phase 3 — inbound health ping,
  same HMAC verifier + nonce keyspace; not wired into any flow yet).
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

## What exists in the app
- Outbound signer (Phase 1): `koya_harness/{sign,headers,client}.py`.
- Inbound mirror verifier (Phase 2): `koya_harness/{verify,config,pii,log}.py`.
- Endpoints: `api/ping.py`, `api/joint_test.py` (Phase 1);
  `koya_harness/api/mirrors.py` (rates/transactions/display_state) +
  `koya_harness/api/joint_test_p2.py` (run_mirror_smoke) (Phase 2);
  `koya_harness/api/{review,health}.py` + shared `api/_responses.py` (Phase 3).
- Phase-3 logic: `koya_harness/risk_render.py` (pure render helpers),
  `koya_harness/audit.py` (best-effort audit writer); v2 risk validation + review-queue
  reconciliation added to `koya_harness/api/mirrors.py`.
- Doctypes (Single, read-only): `Koya Rate Mirror`, `Koya Transaction Mirror`.
- Doctypes (Phase 3, read-only): `Koya Review Item` (per-MANUAL_REVIEW row, snapshot-rebuilt),
  `Koya Harness Audit Log` (append-only, no write/delete perms, `on_trash` blocked).
- Roles (Phase 3): `koya_harness_compliance` (reads Review Item + audit + mirrors),
  `koya_harness_ops` (reads audit + mirrors, NOT Review Item). Operator assigns users later.
- Display: desk Pages `koya-mirror-status` (Phase 2), `koya-review-queue` (Phase 3 review
  console, list + detail), `koya-harness-home` (Phase 3 Operations Console landing); Workspace
  `Koya Harness` for discoverability. All read-only, role-gated, informational stale.
- Tests: `tests/test_{sign,headers,client,risk_render}.py` (30 unit) +
  `tests/test_{verify,mirrors,v2_schema,review_queue,audit_log,roles,landing,health}.py`
  (82 integration) — **112/112 green**.

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

## Next
Phase 3 parallel build is done on the harness side. Awaiting Koya's Phase-3 deploy + the v2
mirror going live, then run joint-test gates 5.2.5–5.2.7: a conversion engineered into
MANUAL_REVIEW appears in the review queue with score + band + full breakdown; the audit log
records the receive; the health ping round-trips signed. No Phase-4 sending side until that
joint test passes.

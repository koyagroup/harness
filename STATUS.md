# Harness — STATUS

> Single source of truth for the harness app's current state. Mirrors the Koya-side
> STATUS so the two builds stay reconcilable. No secret values here — key names only.

**Last updated:** 2026-05-29 (step-03)

## Current phase
**Phase 2 DONE on the harness side — display mirrors live, §6 kill-switch PROVEN.**
Channel live end-to-end since 14:25 (Koya pushes → verifier accepts → displays populate).
Verifier reference-vector test green; full suite 36/36; live signed round-trip green. The
§6 kill-switch joint test passed: with the harness dark (maintenance 503, T+0 14:57:54Z →
restore 15:01:50Z) Koya stayed fully healthy (quote path refreshed mid-outage, worker-slow
unaffected, 0 unhandled rejections, mirror pushes 503+abandoned-no-retry); on restore both
mirrors resumed within cadence (txns +12s, rates +43s) and displays un-staled. See
`docs/progress/step-03.md`.

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

## What exists in the app
- Outbound signer (Phase 1): `koya_harness/{sign,headers,client}.py`.
- Inbound mirror verifier (Phase 2): `koya_harness/{verify,config,pii,log}.py`.
- Endpoints: `api/ping.py`, `api/joint_test.py` (Phase 1);
  `koya_harness/api/mirrors.py` (rates/transactions/display_state) +
  `koya_harness/api/joint_test_p2.py` (run_mirror_smoke) (Phase 2).
- Doctypes (Single, read-only): `Koya Rate Mirror`, `Koya Transaction Mirror`.
- Display: desk Page `koya-mirror-status` (read-only, 15s refresh, informational stale).
- Tests: `tests/test_{sign,headers,client}.py` (12) + `tests/test_{verify,mirrors}.py`
  (24) — 36/36 green.

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
Phase 2 is done on the harness side (build + §6 joint test). Cross-check against Koya's
step-54, then Phase 3 may begin.

# Harness — STATUS

> Single source of truth for the harness app's current state. Mirrors the Koya-side
> STATUS so the two builds stay reconcilable. No secret values here — key names only.

**Last updated:** 2026-05-29 (step-01)

## Current phase
**Phase 2 prep complete — secret separation rotated and proven.** Phase 2 build
proper (the K→H mirror verifier) is the next unit of work and is **not yet started**.

## Wire / secrets state
- Contract: v1 (inbound, LAW) + v1.1 Phase 2 addendum (**PROPOSED**, display mirrors).
- HMAC scheme unchanged: `HMAC-SHA256(secret, ts + "." + nonce + "." + rawBody)`,
  lowercase 64-hex; headers `X-Harness-Timestamp` / `X-Harness-Nonce` /
  `X-Harness-Signature`. Appendix-A vector verified (`f069372a…c8d996`).
- `site_config.json` secret keys:
  - `harness_inbound_secret` — H→K signing (ping/settlement/user-control). **Active.**
  - `harness_outbound_secret` — K→H mirror verification. **Parked** (verifier not built).
  - `harness_shared_secret` — **removed.**
- Code accessor: `get_inbound_secret()` (`koya_harness/config.py`). No
  `get_outbound_secret()` yet (added with the verifier build).

## Last joint test
2026-05-29 — four-outcome inbound test on the rotated secret: **4/4 PASS**
(valid 200 / forged 401 `signature_mismatch` / replay 401 `nonce_replay` /
skew 401 `timestamp_skew`). See `docs/progress/step-01.md`.

## What exists in the app (Phase 1 + this step)
- Outbound signer: `koya_harness/{sign,headers,client}.py`.
- Endpoints: `api/ping.py` (test_connection), `api/joint_test.py` (run_four_outcomes).
- Tests: `tests/test_{sign,headers,client}.py` — 12/12 green.
- **No inbound verification yet** (Phase 2 build).

## Open items / flags
- Re-rotate both secrets before mainnet if this session's transcript is retained
  (values were pasted in-session — see step-01 D3).
- Operator: full `supervisorctl restart` at convenience to bring scheduler/background
  workers onto the new config (web tier already reloaded — step-01 D4).
- Reconcile key names against v1.1 once the contract is signed off (currently PROPOSED).

## Next
Phase 2 build: K→H mirror verifier (`koya_harness.api.mirrors.rates` /
`…transactions`), inbound-mirror nonce store (§1.3), stale-badge UX (§5), kill-switch
joint test (§6).

# Step 01 — Phase 2 prep: inbound-secret rotation + outbound-secret parking

**Date:** 2026-05-29
**Phase:** Phase 2 prep (secret separation), per contract v1.1 addendum §1.2
**Outcome:** ✅ Inbound rotation applied and proven survived (joint test 4/4).
Outbound secret parked for the Phase 2 verifier build.

> No secret values, env-var values, or key material appear in this doc — key
> names and outcomes only. `request_id`s below are wire correlation IDs, not secrets.

---

## 1. Why
Contract v1.1 (Phase 2 "display mirrors" addendum) §1.2 splits the single shared
HMAC secret into two direction-scoped credentials so a leak of one cannot forge
traffic in the other direction:

| Key (`site_config.json`) | Direction | Signs / verifies |
|---|---|---|
| `harness_inbound_secret` (renamed from `harness_shared_secret`, fresh value) | H→K webhooks (ping, settlement, user-control) | harness **signs**, Koya verifies |
| `harness_outbound_secret` (new, fresh value) | K→H mirrors (rates, transactions) | Koya signs, harness **verifies** — Phase 2 verifier, **not built in this step** |

This step is the rotation/prep only: seed both new keys, rename the one code
reference, reload, and prove the **inbound** channel survived. The outbound key is
parked for the verifier build that follows.

## 2. What was done
- **site_config.json** (in `sites/`, outside the app repo — secrets never committed):
  `del(harness_shared_secret)`, added `harness_inbound_secret` and
  `harness_outbound_secret` (values from operator env vars, via `jq`). Confirmed
  the three `harness_` keys present (`harness_inbound_secret`,
  `harness_koya_base_url`, `harness_outbound_secret`); old key absent.
- **Code rename** (commit `c87c200`):
  - `koya_harness/config.py`: `_SECRET_KEY` value → `"harness_inbound_secret"`;
    `get_shared_secret()` → `get_inbound_secret()`; throw message updated.
  - `koya_harness/client.py`: import + call site → `get_inbound_secret`.
  - `api/joint_test.py`: import + call site → `get_inbound_secret`.
  - `tests/test_client.py`: 6 `@patch("…client.get_shared_secret")` targets →
    `get_inbound_secret`.
  - Grep proof: `harness_shared_secret` → 0 hits; `get_shared_secret` → 0 hits.
- **Reload:** see deviation D4. Web tier reloaded onto the new config.

## 3. Verification
- Unit suite (offline signer proof, incl. Appendix-A reference vector
  `f069372a…c8d996`): **12/12 pass**.
- Console check on a fresh process: imports OK; `harness_inbound_secret` present;
  `harness_outbound_secret` present; `harness_shared_secret` absent;
  `get_inbound_secret()` returns truthy.
- Web health post-reload: `frappe.ping` → `{"message":"pong"}` 200; 9 fresh workers.
- **Four-outcome joint test on the rotated secret (harness-side run):**
  | Outcome | Status | Code / detail |
  |---|---|---|
  | 1 valid | 200 | `ok:true`, rid `49603445b4334d9a8fd417a31a5a46c3`, received_at `2026-05-29T12:37:24.739Z` |
  | 2 forged | 401 | `signature_mismatch` |
  | 3 replay | 200 → 401 | `nonce_replay` on the second send |
  | 4 skew | 401 | `timestamp_skew` |

  Koya operator independently reported the same 4/4 in the same window.
  **Outcome 1 succeeding is the proof both sides are on the new inbound value.**

## 4. Deviations surfaced (never silently worked around)
- **D1 — Contract presence/status.** The `cto/` docs were not on this box at recon;
  the v1.1 addendum (provided in-session) is **PROPOSED for both-sides sign-off**,
  not finalized. Key names taken from §1.2 verbatim. Reconcile when signed.
- **D2 — No prior step docs / STATUS.md.** None existed (single Phase 1 commit). The
  playbook's "previous rotation doc (step-50)" did not exist — this is the *first*
  rotation and the *first* step doc; the `docs/progress/` tree + `STATUS.md` were
  created here. Numbered `step-01`.
- **D3 — Secret values pasted into the session chat** rather than read solely from
  operator env vars. The values reached `site_config.json` only (never a commit,
  log, or this doc), but they now exist in the assistant transcript. **Recommend
  re-rotating both secrets before mainnet** if the transcript is retained.
- **D4 — `bench restart` unavailable.** It shells out to `sudo supervisorctl`, and
  sudo is not available to the app user. Reloaded the web tier via a graceful
  gunicorn `SIGHUP` to the master (PID 21196) instead — zero-downtime, 9 workers
  cycled to fresh PIDs. Supervisor-managed scheduler/background workers were *not*
  cycled; immaterial for Phase 1 (no harness background/scheduled signing path). A
  full `supervisorctl restart` by the operator will bring those onto the new config.
- **D5 — Recon grep gap.** The initial recon grepped only the key string
  `harness_shared_secret` and missed 6 `get_shared_secret` `@patch` targets in
  `tests/test_client.py`. Caught by the added `grep -rn "get_shared_secret"` step,
  which is why the plan included it. Tests would otherwise have failed on a stale
  patch target.

## 5. Boundaries honored (CLAUDE.md §2)
No key material in the repo (values live in env / `site_config.json` only), no
signing capability added, no quote-hot-path code, no amount/destination fields, and
the outbound **verifier was not built** — only the `harness_outbound_secret` key was
parked. Pure rotation + rename.

## 6. Cleanup
- Backup `site_config.json.bak-pre-p2-rotation` (held the OLD inbound secret)
  **deleted** after the 4/4 pass.

## 7. Next
Phase 2 build proper — the K→H mirror verifier (verifies rates/transactions mirrors
signed with `harness_outbound_secret`), per contract v1.1:
- Frappe-native receive endpoints `koya_harness.api.mirrors.rates` /
  `…transactions` with the v1 §2 verification step order (structural → skew →
  signature → replay).
- Nonce-replay store on the inbound-mirror endpoints (§1.3, keyspace
  `harness:outbound-nonce:{nonce}`, 600 s TTL).
- Stale-badge UX (§5) and the kill-switch boundary joint test (§6, Koya functions
  fully with the harness down). One phase at a time — do not start before this
  step's joint test is recorded (it is: §3 above).

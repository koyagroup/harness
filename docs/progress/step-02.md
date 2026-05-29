# Step 02 — Phase 2 build: K→H mirror verifier, doctypes, endpoints, display

**Date:** 2026-05-29
**Phase:** Phase 2 (display mirrors), per Wire Contract v1.1 addendum (now checked in at
`cto/HARNESS_WIRE_CONTRACT_v1.1_phase2.md`).
**Outcome:** ✅ Harness receive side built and proven end-to-end in-process and over live
HTTP. Verifier reference-vector test green; full suite 36/36. Live joint test (push-lands /
stale / kill-switch) **staged** pending Koya's mirror sender + egress-IP allowlisting.

> No secret values or key material appear in this doc — key names and outcomes only.
> `request_id`s below are wire/receipt correlation IDs, not secrets.

---

## 1. Why
Koya pushes signed display mirrors (rates ~30s, transactions ~60s) one-way, fire-and-
forget. The harness verifies them with the **separate** `harness_outbound_secret`, stores
the latest snapshot (overwrite, no history), shows it to staff read-only with an
informational stale badge, and participates in the kill-switch joint test by being a clean
stop/restart. Mirror data is **read-only display** — never read back as authoritative for
any harness decision.

## 2. What was built
All Phase-2 crypto/logic lives in the established `harness.koya_harness.*` namespace
(reusing the Phase-1 `compute_signature` verbatim — no HMAC duplication):

- **Verifier** `harness/koya_harness/verify.py` — `verify_outbound_signed_request(request)`
  implementing the v1 §2 step order: headers present → format → content-type/size → skew →
  `hmac.compare_digest` signature → atomic Redis `SET NX EX 600` replay
  (keyspace `harness:outbound-nonce:`). rawBody is `request.get_data()` literal bytes,
  never re-serialized. Mints a harness-side correlation id per request; secret read at
  request time.
- **Config** `harness/koya_harness/config.py` — added `get_outbound_secret()`
  (reads `harness_outbound_secret`; throws with the key name, never the value).
- **PII guard** `harness/koya_harness/pii.py` — `scan_recent_for_pii()` (forbidden keys:
  email, phone, name, user_id, customer_id, ip_address, device_id, device_fingerprint).
  Warn-and-store, never reject; returns key names only.
- **Logger** `harness/koya_harness/log.py` — koya_harness logger pinned to INFO (Frappe's
  default is ERROR, which would drop receipt/PII lines).
- **Endpoints** `harness/koya_harness/api/mirrors.py` — `rates()` / `transactions()`
  (`allow_guest=True`; auth is HMAC + edge allowlist, not Frappe sessions) and
  `display_state()` (staff). Validate §2.3/§3.3 (schema_version, snapshot_at, arrays,
  decimal-string sanity), upsert the Single doctype with `received_at`, return the §6
  envelope. Never throw uncaught → 500 `internal_error` envelope.
- **Doctypes** (module Harness, both `issingle`, read-only): `Koya Rate Mirror`
  (request_id, schema_version, snapshot_at, received_at, last_source, rates_json) and
  `Koya Transaction Mirror` (… status_counts_json, recent_json, recent_count, pii_warning).
- **Display** desk Page `koya-mirror-status` (`harness/harness/page/koya_mirror_status/`):
  two read-only cards, 15s auto-refresh + manual refresh, never-blank, informational amber
  stale badge (90s rates / 180s txns), status-counts grid, recent table, PII notice. No
  actions, no Koya calls, no nav links.
- **Joint-test driver** `harness/koya_harness/api/joint_test_p2.py` — `run_mirror_smoke()`
  returns both mirrors' receipt state for paste-back.
- **Tests** `harness/tests/test_verify.py` (15) and `harness/tests/test_mirrors.py` (9).

## 3. Verification
- **Verifier suite — `bench run-tests --module harness.tests.test_verify`: 15/15.**
  Names: reference_vector_accepts (THE gate — same Appendix-A `f069372a…c8d996` accepted
  with the outbound secret), valid_fresh_request_accepts, wrong_signature, nonce_replay,
  stale_timestamp, future_timestamp, missing_each_header, malformed_signature_uppercase,
  malformed_signature_wrong_length, malformed_nonce, unsupported_content_type,
  charset_suffix_tolerated, empty_body, body_too_large, **reserialized_body_fails**
  (verify-what-you-received invariant).
- **Endpoint suite — `--module harness.tests.test_mirrors`: 9/9.** valid rates stored;
  valid transactions stored (counts + recent); **PII guard warns-and-stores** (key name
  only, no value); **second push overwrites first** (snapshot mode, stored == 2nd exactly);
  schema-validation 400s; forged signature 401.
- **Full app — `bench run-tests --app harness`: 36/36** (24 Phase-2 integration + 12
  Phase-1), green and idempotent across back-to-back runs.
- **Live signed HTTP smoke** (real gunicorn on 127.0.0.1:8000, `Host: kronos.koyabank.com`,
  secret read in-process — never printed):
  | Case | HTTP | code |
  |---|---|---|
  | valid rates | 200 | `ok:true` |
  | forged sig | 401 | `signature_mismatch` |
  | replay (same nonce) | 401 | `nonce_replay` |
  | skew (ts−3600) | 401 | `timestamp_skew` |
  | missing header | 400 | `missing_required_headers` |
  | bad content-type | 400 | `unsupported_content_type` |
  | valid transactions | 200 | `ok:true`, stored |
  | transactions + injected `email`/`phone` | 200 | stored anyway; `pii_warning` = "email, phone"; WARNING logged (key names only); **no value leaked to logs** |
  | two pushes | — | second overwrote first |
- Doctypes confirmed Single; Page `koya-mirror-status` synced; `display_state` and
  `run_mirror_smoke` return correct receipt + staleness state.
- Ruff: all checks pass.

## 4. Deviations surfaced (never silently worked around)
- **D1 — Endpoint path vs contract §2.1/§3.1 (needs Koya sign-off).** The contract writes
  the routes as `POST /harness/internal/rates/mirror` (generic). The build was specified as
  Frappe-native whitelisted methods, and the operator chose the `koya_harness.api.mirrors.*`
  segment. **But Frappe's `frappe.get_attr` (frappe/__init__.py:1113) requires the leading
  segment of a `/api/method/<path>` to be an *installed app*** — and `koya_harness` is a
  package, not an installed app (only `harness` is). A top-level `koya_harness.*` path
  raises `AppNotInstalledError`. **Resolution:** endpoints live at
  `harness.koya_harness.api.mirrors.*`, reachable at the exact URLs Koya must POST to:
  - `POST /api/method/harness.koya_harness.api.mirrors.rates`
  - `POST /api/method/harness.koya_harness.api.mirrors.transactions`

  This preserves the chosen `koya_harness.api.mirrors` segment (app-prefixed). **Flag:** the
  contract §2.1/§3.1 path strings should be reconciled to these whitelist URLs on both-
  sides sign-off (the harness has no custom URL router; whitelist methods are the binding).
- **D2 — Malformed-JSON → 417 before our handler.** Frappe's `application/json` middleware
  parses the body into `form_dict` and returns **417 DataError** for a non-JSON body
  *before* the whitelisted method (and thus before HMAC verification) runs. So our
  in-handler `validation_error` for "body is not valid JSON" is unreachable over HTTP
  (still safely 4xx-rejected). A *valid-JSON-but-bad-schema* body reaches the handler →
  400 `validation_error`; a *valid-JSON bad-signature* body reaches it → 401
  `signature_mismatch` (confirmed live). Only the non-JSON-bytes case short-circuits to 417
  without a §6 envelope — acceptable (rejected), noted for both sides.
- **D3 — Response envelope wrapping.** Frappe returns whitelisted-method results as
  `{"message": <envelope>}` with the HTTP status set on `frappe.local.response`. Per v1.1
  §2.4 Koya keys on the status code (success body ignored, failure body only logged), so
  the wrapper is harmless. The §6 envelope is intact under `message`.
- **D4 — Config toggles (dev bench).** Enabled `developer_mode=1` (sync doctype/Page JSON
  via migrate) and `allow_tests=true` (run the suite) in `site_config.json`. Not secrets;
  the operator may set `allow_tests` back to false after verification.
- **D5 — Correction of a step-recon claim.** An exploration pass flagged
  `koya_harness/client.py:51` `except ValueError, AttributeError:` as a Python-2 syntax
  bug. **This is incorrect:** Python 3.14 (PEP 758) accepts unparenthesized multi-exception
  `except` and catches both — verified at runtime on this interpreter (3.14.5). No bug, no
  change made.
- **D6 — Carried open from step-01.** (a) Re-rotate both secrets before mainnet if the
  step-01 transcript is retained (values were pasted in-session then). (b) The live gunicorn
  workers imported the mirror module at first request; the final logger-level code is proven
  **in-process** but a full `supervisorctl`/worker restart by the operator is needed to make
  the latest module live over HTTP (same no-sudo constraint as step-01 D4). This also
  applies before the live joint test.

## 5. Boundaries honored (CLAUDE.md §2)
Read-only display only — no signing, no key material in the repo, no BitGo/wallet/AWS,
no quote-hot-path code, no amount/destination ingress. Mirror data is **never read back**
as authoritative: a grep of `koya_harness/` shows the snapshots are only written by the
receivers and read by `display_state` / `run_mirror_smoke` (display + joint-test query) —
no decision path consumes them. `allow_guest=True` is intentional: auth is HMAC + edge IP
allowlist, not Frappe sessions. PII guard is defense-in-depth (warn-and-store); Koya
remains the contract enforcer.

## 6. Joint test (§6) — STAGED, not yet run
Offline halves are proven (reference vector + live signed round-trip against our own
gunicorn). The live cross-system gates require Koya's worker-slow mirror sender live AND
Koya's egress IP(s) allowlisted at the harness edge for the two
`harness.koya_harness.api.mirrors.*` paths. Procedure when both are ready:
- **Push-lands:** `bench execute harness.koya_harness.api.joint_test_p2.run_mirror_smoke`
  → rates `received_at` within 30s, transactions within 60s; display fresh, no badge.
- **Stale-badge:** Koya pauses ~120s/210s → amber informational badge appears, data stays
  shown; resume → badge clears within one cadence.
- **Kill-switch (the gate):** operator stops the bench; Koya proves quote path, state
  machine (testnet txid), and BitGo poller continue and mirror pushes are logged+abandoned
  (no retry/backpressure); operator restarts; mirrors resume, display un-stales.
- **Koya grep proof (their side):** zero mirror reads in their money path. Harness has no
  analogous path by design.

## 7. Next
- Operator: allowlist Koya's egress IP(s) at the harness edge for the two mirror paths;
  full worker restart to bring the latest module live over HTTP.
- Run the §6 joint test with Koya; record timestamps here. Phase 2 is done on the harness
  side, blocking only on the live joint test + Koya's grep-proof confirmation.
- Do not start Phase 3+ until the Phase-2 joint test is recorded.

# Step 04 — Phase 3 parallel build (v2 receiver + review console + app backbone)

**Date:** 2026-05-30
**Branch:** `feat/p3-parallel`
**Scope:** HARNESS-P3-PARALLEL, gates G1–G7. Everything contract-frozen or Koya-independent
on the harness side, built during Koya's Phase-3 deploy window so the eventual joint test is
"real data flows into a finished UI." No Phase-4 sending side, no live calls to Koya, no
contract edits, no `developer_mode`/`allow_tests` changes.

**Headline:** all six build gates done; **112 tests green** (82 integration + 30 unit), up
from Phase-2's 36. Awaiting Koya's Phase-3 deploy + v2 mirror live for joint-test gates
5.2.5–5.2.7.

---

## G1 — v2 risk schema on the transactions receiver
**Built** (`koya_harness/api/mirrors.py`): `validate_risk_object(risk) -> (ok, error_code)`
(score 0–100, scorer_version ≥ 1, band str, computed_at RFC3339, breakdown rows with
`value: str|int|float|None` **uncoerced**, weight ≥ 0, contribution ∈ [0,weight]),
`risk_warnings()` (band/signal-name warnings, **no values**), `_collect_risk_warnings()`.
The receiver runs the risk pass keyed on **`"risk" in item` per item** — never on
`schema_version` — and **warns-and-stores** (a malformed risk object is logged with
codes/signal-names only and still stored).

**Verification:** `tests/test_v2_schema.py` **23/23**. Grep confirms `schema_version` in the
receiver appears only in storage / int-validation / display — **no value branching**.

## G2 — review-queue console (read-only)
**Built:**
- DocType **`Koya Review Item`** (regular, `autoname: field:ref`, all fields read-only,
  `read_only:1`; perms System Manager + `koya_harness_compliance`).
- **`koya_harness/risk_render.py`** — pure, frappe-free, total render helpers
  (`value_for_signal`, `format_kes`, `band_class`, `top_signal`, `sort_breakdown`,
  `render_breakdown_html`). Unknown signal/band/value-type → render, never raise.
- **`koya_harness/api/review.py`** — `review_queue_state()` + `review_item_detail()`,
  session-gated AND server-side `has_permission`-gated.
- **Snapshot reconciliation** in `transactions()`: validate → upsert (MANUAL_REVIEW + `risk`
  only) → delete-missing, best-effort, single commit. Queue rebuilt per push.
- **Page `koya-review-queue`** — route-driven list + detail (`#koya-review-queue/<ref>`),
  reuses the Phase-2 stale-pill (180s) + style language. **No approve/reject UI.**

**Verification:** `tests/test_risk_render.py` **18/18** (incl. the G2.6 gate: unknown signal
→ non-empty string) + `tests/test_review_queue.py` **11/11**. A rendered detail-table dump
against a mixed payload confirmed contribution-desc sort, money/count/boolean dispatch, an
unknown signal rendered verbatim, a null value as "—", and a zero-contribution row marked
`krq-bd-row--muted` (shown, not hidden).

## G3 — append-only audit log
**Built:** DocType **`Koya Harness Audit Log`** (read-only fields; no write/create/delete
perm for any role; `on_trash` hard-throws). **`koya_harness/audit.py`** `write_audit()` —
best-effort (try/except), `detail_json` = key names + counts only. Wired into `rates()`
(`mirror_rates_received`), `transactions()` (`mirror_transactions_received` + a
`mirror_risk_validation_warning` row when a G1 warning fires), and `health.ping()`
(`health_ping_received`).

**Verification:** `tests/test_audit_log.py` **7/7** — one row per receive; two on a risk
warning; `detail_json` proven free of the KES amount + the ref; a mocked audit failure
leaves the receive `ok:True`; delete blocked; no write/create/delete perms.

## G4 — staff roles
**Built:** `koya_harness_compliance` + `koya_harness_ops`, **auto-created on migrate** from
doctype permission tables (`make_module_and_roles`) — no fixtures hook, no `hooks.py`
change. Mirror doctype JSONs extended to grant both roles read.

Permission matrix (all write/create/delete = 0): Review Item → SM + compliance (ops
**absent**); Audit Log + both mirrors → SM + compliance + ops.

**Verification:** `tests/test_roles.py` **7/7** — both roles exist; real-user
`has_permission` proves ops cannot read Review Item while compliance can; both read mirrors
+ audit.

## G5 — Koya Operations Console landing page
**Built:** Page **`koya-harness-home`** — banner with prominent connection status, then
Mirror Status (both roles), Review Queue (compliance/SM only, gated in JS **and** backed by
the server-side `review_queue_state` perm gate), Audit Log link (either role). Workspace
**"Koya Harness"** for sidebar discoverability (shortcuts to console / review queue / mirror
status / audit log), gated at the whole-workspace level. Both auto-synced from the module
folder (no fixtures fallback needed).

**Verification:** `tests/test_landing.py` **4/4** — real ops user → `review_queue_state`
`permitted:false` (no section); real compliance user → `permitted:true`; page + workspace
exist and carry the {SM, compliance, ops} role gate.

## G6 — inbound health-ping receiver
**Built:** **`koya_harness/api/health.py`** `ping()` (`allow_guest=True`) — reuses
`verify_outbound_signed_request` verbatim (same outbound secret + `harness:outbound-nonce:`
keyspace). Optional `{"echo": str}`; returns `{"ok": true, "data": {"echo", "received_at":
<rfc3339 Z>, "harness_request_id": <uuid>}}`; writes a `health_ping_received` audit row.
Extracted shared §6-envelope helpers into **`koya_harness/api/_responses.py`** (imported by
both `mirrors.py` and `health.py`).

**New endpoint:** `POST /api/method/harness.koya_harness.api.health.ping`.

**Verification:** `tests/test_health.py` **6/6** (valid→echo, empty echo→null, non-string
echo→400, forged→401 signature_mismatch, replay→401 nonce_replay, audit row). Live HTTP:
unsigned POST → `HTTP 400` + §6 `missing_required_headers` envelope (route wired, verifier
runs, workers current). The full **signed** HTTP round-trip is staged with the Koya joint
test (needs Koya's signer + egress allowlist).

---

## Test counts
- **Unit (30):** test_sign 1, test_client 6, test_headers 5, **test_risk_render 18**.
- **Integration (82):** test_verify 15, test_mirrors 9, **test_v2_schema 23**,
  **test_review_queue 11**, **test_audit_log 7**, **test_roles 7**, **test_landing 4**,
  **test_health 6**.
- **Total 112**, all green. (Phase 2 was 36.) Run as
  `bench --site kronos.koyabank.com run-tests --app harness` (this bench reports the unit and
  integration categories separately: "Ran 82" + "Ran 30").

## Deviations surfaced (none silently worked around)
1. **Detail view = custom Page** (the queue page swaps into a detail view routed by
   `?item=<ref>`), chosen over a DocType form — operator decision during planning. All
   value-dispatch/sort/band logic lives in `risk_render.py` (Python, unit-tested).
2. **`_naive_dt()` for typed Datetime columns (G2).** `_parse_snapshot_at` returns a
   tz-aware datetime (`+00:00`), which MariaDB rejects for a real DATETIME column. The
   Phase-2 Single mirror doctypes never hit this because Singles store every field as text
   in `tabSingles` — so it was latent. Added `_naive_dt()` (strips tz, keeps the Koya UTC
   wall-clock; fields labelled "(Koya)") for `Koya Review Item`'s `created_at`/`updated_at`/
   `risk_computed_at`. `_parse_snapshot_at` is unchanged → Phase-2 behaviour untouched.
3. **Non-int `score` → Frappe Int default `0` (G2).** A non-int score (already a G1 contract
   warning) cannot null a non-nullable Int field; it stores as 0. Degraded, never a crash;
   documented in `test_non_int_score_row_kept_degraded`.
4. **Roles via `make_module_and_roles`, not fixtures (G4).** Roles named in committed doctype
   permissions are auto-created on migrate — no `fixtures` hook, no `hooks.py` change. The
   only declarative source of truth is the permission tables (no drift risk).
5. **`_responses.py` extraction (G6).** Shared §6-envelope helpers factored out so `health`
   does not import private names from `mirrors`. `internal_error` message generalised from
   "handling the mirror push" to "handling the request" (informational text only; Koya keys
   on code + status).
6. **`hooks.py` unchanged.** Doctypes, pages, and the workspace all auto-sync from the module
   folder on this bench — confirmed at migrate, so the planned `fixtures = ["Workspace"]`
   fallback was not needed.

## What is NOT built (bounded scope)
- **Phase-4 approve/reject sending side** — no UI buttons, no webhook to Koya, no signing.
- **Live integration against Koya** — Koya is mid-deploy; the live signed round-trips for the
  v2 mirror and the health ping are the joint-test gates, staged not run.
- Contract path-string reconciliation (housekeeping for sign-off, not this build).
- No `developer_mode` / `allow_tests` change (pre-mainnet hardening sweep owns those).

## Carry-over debt (unchanged from step-03)
- Re-rotate both secrets pre-mainnet (chat-exposed in earlier steps).
- `developer_mode=1` + `allow_tests=true` intentionally held per Koya's guidance.
- Endpoint path text vs contract §2.1/§3.1 — reconcile on sign-off.

## Next
Await Koya's Phase-3 deploy + v2 mirror live, then run joint-test gates 5.2.5–5.2.7: a
conversion engineered to score into MANUAL_REVIEW appears in the review queue with score +
band + full breakdown; the audit log records the receive; the health ping round-trips signed.

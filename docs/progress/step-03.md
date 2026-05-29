# Step 03 — Phase 2 §6 kill-switch joint test: PASSED

**Date:** 2026-05-29
**Phase:** Phase 2 (display mirrors) — the §6 kill-switch boundary joint test, the gate
that closes Phase 2.
**Outcome:** ✅ **Kill-switch boundary PROVEN end-to-end.** Koya stayed fully healthy with
the harness dark; the harness degraded cleanly (503, no retry) and auto-resumed within
cadence on restore. Phase 2 is now **done on both sides**, pending only doc cross-check.

> Times below are UTC (`Z`); the box clock is EAT (UTC+3), shown where receipts are quoted.

## Context
The channel went live end-to-end at 14:25 (Koya's worker-slow mirror sender pushing,
harness verifier accepting, edge allowlist open, displays populating). With the
push-lands half already green, this step ran the §6 gate: **Koya must function fully when
the harness is unreachable.**

## Method (and why)
The harness web tier is supervisor-managed and `supervisorctl` is permission-denied to the
app user (no sudo — step-01 D4), so a held process-level stop wasn't available (supervisor
would auto-respawn gunicorn). The reversible lever used was **Frappe maintenance mode**
(`bench set-maintenance-mode on/off`) → whole-site **503**, which is equivalent to "bench
stopped" for the mirror channel (Koya sees a clean non-2xx push failure per v1.1 §2.4).
Verified reversible by a pre-test probe before the coordinated window. The kill was run as
a guarded background job with an EXIT-trap that forces maintenance OFF on any exit, so the
harness could not be left down by an interrupted session.

## Timeline (joint, both sides)
| Phase | Time (UTC / EAT) | Observation |
|---|---|---|
| Baseline | 14:57:32Z / 17:57:32 | rates+txns fresh, verifier accepting |
| **T+0 — harness dark** | **14:57:54Z / 17:57:54** | maintenance ON; harness returns 503 |
| Outage (Koya-side) | 14:58:02–14:59:04Z | 4 mirror push ticks → 503 SessionStopped, each "abandoned, no retry" |
| **Restore** | **15:01:50Z / 18:01:50** | maintenance OFF (~3m56s outage); harness immediately serving (400 on unsigned probe, no propagation lag) |
| txns mirror resumed | ~15:02:02Z (+12s) | next 60s cycle landed → 200, stored |
| rates mirror resumed | ~15:02:33Z (+43s) | next 30s cycle landed → 200, stored |
| Both un-stale | 15:02:39Z | display recovered |
| Final check | 15:03:06Z | rates age 3s, txns age 6s, both `stale:false`, maintenance flag 0 |

## Koya-side proof (reported by the Koya CTO, recorded for reconciliation)
Two live samples during the outage (14:58:43Z, 14:59:32Z) + continuous log evidence:
- **API health:** 200 / ~0.225s (== baseline).
- **Quote BTC-KES:** 200, `stale:false`, and it **refreshed mid-window** (mid 9,452,989 →
  9,450,892) — Koya's rate aggregator is fully live with the harness down. **This is §6's
  core proof: the money/quote path is independent of the mirror.**
- **worker-slow:** RUNNING throughout (started 14:24:07, 1/1), BitGo poller and other jobs
  unaffected.
- **unhandledRejection / Uncaught / SIGTERM / SIGKILL / FATAL / restart events: 0.**
- Mirror transition clean: 200 through 14:57:32 → 503 from 14:58:02 onward, every failure
  logged + abandoned with no retry, no backpressure, no queue.

## Harness-side proof
- T+0 503 confirmed live; restore at 15:01:50Z; `run_mirror_smoke` shows both mirrors
  resuming within one cadence (txns +12s, rates +43s) and going `stale:false`; display
  un-stales automatically. No harness code ran during the outage (it was 503) and none was
  needed on resume — the next snapshot simply overwrote, per snapshot-mode design.
- Harness has no analogous money path to grep (by design); the §7 grep proof is Koya-side.

## Deviations / notes
- **Method = maintenance mode (whole-site 503), not a process stop** — see Method above.
  Blast radius is the whole kronos site for the window (equivalent to bench-stop). No
  harness-only route block was possible without sudo.
- **A ~40s rates blip occurred before T+0** from the lever-verification probe; it was
  flagged to Koya in advance and excluded from the test window.
- **D1 (path) resolved in practice:** Koya's sender pushes to the actual reachable
  whitelist URLs `/api/method/harness.koya_harness.api.mirrors.{rates,transactions}` and
  has been getting 200s since 14:25 — both sides agree on the wire URL. The contract
  §2.1/§3.1 *path strings* still want a text reconciliation to match (see step-02 D1), but
  the integration itself is proven.

## Result
**Phase 2 §6 kill-switch gate: PASSED.** Combined with step-02 (verifier reference-vector
green, 36/36 suite, live signed round-trip, doctypes, display, PII guard), Phase 2 is
**done on the harness side**. Koya records the mirror side in their step-54.

## Next
- Carry-over flags remain open (step-02 §4): re-rotate both secrets before mainnet if the
  session transcripts are retained; operator may set `allow_tests` back to false;
  reconcile contract §2.1/§3.1 path strings to the whitelist URLs on sign-off.
- Phase 3 may begin once both sides' Phase-2 step docs are cross-checked.

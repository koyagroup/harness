# Step 11 — Keep kronos.koyabank.com out of all search indexes (security)

**Date:** 2026-05-31
**Branch:** `fix/noindex`

kronos is an INTERNAL control-plane app that was found indexed by a search engine. Added two
code-side signals (can't be reverted from the UI), applied site-wide (all apps' routes on the site):

## Done
- **`after_request` hook** `harness.api.noindex.set_no_index_headers` → stamps
  **`X-Robots-Tag: noindex, nofollow, noarchive, nosnippet, noimageindex`** on EVERY response
  (web / desk / api). Authoritative de-index signal; best-effort (can never break a response).
- **`after_migrate` hook** `harness.api.noindex.enforce_robots_txt` → pins
  **`Website Settings.robots_txt = "User-agent: *\nDisallow: /"`** (the source `frappe/www/robots.py`
  renders at `/robots.txt`). Applied immediately + re-enforced on every migrate.
- Wired in `harness/hooks.py`; web tier reloaded so the header is live now.

## Verified (HTTP, Host: kronos.koyabank.com)
- `X-Robots-Tag: noindex,…` present on `/`, `/app`, `/api/method/frappe.ping`, `/login`.
- `/robots.txt` → `User-agent: *` / `Disallow: /`.

## Important nuances (operational — flagged to the operator)
1. **robots.txt vs noindex for ALREADY-indexed URLs:** `Disallow: /` blocks crawlers from
   *fetching* pages, so they won't *see* the `noindex` header → existing indexed URLs can linger as
   URL-only entries. To remove them: submit a **Search Console / Bing Webmaster "Removals"** request
   for the domain; OR temporarily allow crawl (drop the Disallow) so Google re-crawls, sees
   `noindex`, and drops them — then re-block. The `X-Robots-Tag` header is the durable "never index"
   guarantee for future crawls.
2. **The real fix is network-level:** an internal app should not be internet-reachable. Put kronos
   behind the edge IP-allowlist / auth (nginx / ALB / Cloudflare) so crawlers can't reach it at all.
   These header/robots signals are defense-in-depth, not a substitute.

## Scope
Site-wide by design (the whole internal site must not be indexed). No money-path / contract /
live-fire change. This is the harness app's `after_request`/`after_migrate` hooks (they run for all
requests on the site because harness is installed on it).

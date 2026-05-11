# Plan: SEO follow-up for the /research + /resources restructure

**Status**: Ready to start
**Created**: 2026-05-11
**Updated**: 2026-05-11 -- restructured for agent execution

## Summary

The May 2026 restructure moved eight research subsections + `/faq` under
`/research/` and introduced a new `/resources/` editorial section. Astro
emits the redirects as `<meta http-equiv="refresh">` because GitHub Pages
cannot serve real 301s. Cloudflare is in front of the site, so we *can*
serve 301s -- and should, both to consolidate signals on the old URLs and
to avoid the perceptual hop on direct hits.

This plan is structured for execution by automation agents (Bash + REST,
plus Chrome-controlled browser for the few operations that have no API).
Each section lists prerequisites, exact commands, and acceptance criteria.

Five workstreams:

1. Replace meta-refresh redirects with real 301s at Cloudflare (REST).
2. Refresh `docs/seo-and-cloudflare-playbook.md` to match the new URL layout (file edit).
3. Add layout-driven JSON-LD to `/resources/*` pages (code).
4. Audit internal links for legacy paths (grep + edit).
5. GSC verification + watch (API for sitemap/inspection, browser for Request Indexing).

Out of scope: changing the alpha `noindex` policy for research detail
pages, redesigning the homepage, or building per-article OG images.

## Why now

- The restructure shipped on `1e41422` (2026-05-09). Google has not yet
  recrawled most of the old URLs, so the consolidation signal is most
  valuable in the next 2-4 weeks.
- `/resources/` is the first chunk of editorial content on the site --
  it's indexable from day one, and the how-to / decision-tool format is
  exactly what Google likes to surface.

---

## 0. Prerequisites (human, one-time)

These cannot be done by an agent. Complete them before launching the
automation runs.

### 0.1 Cloudflare API token

Create a token at <https://dash.cloudflare.com/profile/api-tokens>:

- Permissions:
  - **Account** -> **Account Filter Lists** -> **Edit**
  - **Account** -> **Bulk URL Redirects** -> **Edit**
  - **Account** -> **Account Rulesets** -> **Edit**
- Account resources: include the account that owns `dangerousrobot.org`.
- No zone permissions needed.

Export for agent use:

```sh
export CF_API_TOKEN=...
export CF_ACCOUNT_ID=...   # from dash.cloudflare.com URL or accounts_list MCP tool
```

### 0.2 GSC service account

1. In GCP console: create (or reuse) a project, enable
   "Google Search Console API", create a service account, generate a JSON
   key. Save to `~/.config/dr-seo/gsc-service-account.json` (gitignored).
2. In GSC, open property `sc-domain:dangerousrobot.org` -> **Settings ->
   Users and permissions -> Add user**. Paste the service account email
   (`xxx@yyy.iam.gserviceaccount.com`); permission **Owner**.
3. Verify by minting a token:

   ```sh
   gcloud auth activate-service-account --key-file=~/.config/dr-seo/gsc-service-account.json
   export GSC_TOKEN=$(gcloud auth print-access-token)
   ```

### 0.3 Persisted Chrome profile (only for section 5.3)

Sign in once to <https://search.google.com/search-console> in the Chrome
profile the browser MCP uses. Persist cookies. Do not script the Google
login -- Google's bot detection will lock the account.

---

## 1. Cloudflare 301 redirects (REST API, agent-executable)

Astro's redirects emit static HTML files with `<meta http-equiv="refresh"
content="0; url=...">`. Search engines do follow them, but a real 301 is
unambiguous and faster for users. The Cloudflare MCP does **not** cover
Bulk Redirects -- use the REST API directly.

### 1.1 Redirect list (source of truth: `astro.config.ts`)

| Source URL (no scheme) | Target | subpath_matching |
|---|---|---|
| `dangerousrobot.org/faq` | `https://dangerousrobot.org/research` | false |
| `dangerousrobot.org/claims` | `https://dangerousrobot.org/research/claims` | false |
| `dangerousrobot.org/claims/` | `https://dangerousrobot.org/research/claims/` | true |
| `dangerousrobot.org/entities/` | `https://dangerousrobot.org/research/entities/` | true |
| `dangerousrobot.org/companies` | `https://dangerousrobot.org/research/companies` | false |
| `dangerousrobot.org/products` | `https://dangerousrobot.org/research/products` | false |
| `dangerousrobot.org/subjects` | `https://dangerousrobot.org/research/subjects` | false |
| `dangerousrobot.org/topics` | `https://dangerousrobot.org/research/topics` | false |
| `dangerousrobot.org/topics/` | `https://dangerousrobot.org/research/topics/` | true |
| `dangerousrobot.org/sources` | `https://dangerousrobot.org/research/sources` | false |
| `dangerousrobot.org/sources/` | `https://dangerousrobot.org/research/sources/` | true |
| `dangerousrobot.org/criteria` | `https://dangerousrobot.org/research/criteria` | false |
| `dangerousrobot.org/criteria/` | `https://dangerousrobot.org/research/criteria/` | true |

All rows: `status_code: 301`, `preserve_query_string: true`. Wildcard
rows additionally: `preserve_path_suffix: true`.

Note: literal `*` is not supported in `source_url`. The "wildcard"
behavior is the `subpath_matching: true` flag, which makes
`/claims/` match the entire subtree.

### 1.2 Execution -- agent recipe

Place the list above into `scripts/seo/redirects.json` as a JSON array
matching Cloudflare's item schema. Example two rows (one static, one
wildcard):

```json
[
  {"redirect":{"source_url":"dangerousrobot.org/faq","target_url":"https://dangerousrobot.org/research","status_code":301,"preserve_query_string":true}},
  {"redirect":{"source_url":"dangerousrobot.org/claims/","target_url":"https://dangerousrobot.org/research/claims/","status_code":301,"subpath_matching":true,"preserve_path_suffix":true,"preserve_query_string":true}}
]
```

Then run the following idempotent sequence. Every step checks for an
existing resource by name/ref before creating.

```sh
set -euo pipefail
AUTH="Authorization: Bearer $CF_API_TOKEN"
CT="Content-Type: application/json"
API="https://api.cloudflare.com/client/v4"
LIST_NAME="dr_redirects"
RULE_REF="dr_redirects_rule"

# (a) Find or create the redirect list
LIST_ID=$(curl -sS -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rules/lists" \
  | jq -r --arg n "$LIST_NAME" '.result[] | select(.name==$n and .kind=="redirect") | .id' | head -1)
if [ -z "$LIST_ID" ]; then
  LIST_ID=$(curl -sS -X POST -H "$AUTH" -H "$CT" \
    "$API/accounts/$CF_ACCOUNT_ID/rules/lists" \
    -d '{"name":"'"$LIST_NAME"'","description":"dangerousrobot.org restructure 301s","kind":"redirect"}' \
    | jq -r .result.id)
fi
echo "LIST_ID=$LIST_ID"

# (b) Replace items in the list (PUT replaces; safe to rerun)
OP=$(curl -sS -X PUT -H "$AUTH" -H "$CT" \
  "$API/accounts/$CF_ACCOUNT_ID/rules/lists/$LIST_ID/items" \
  --data @scripts/seo/redirects.json | jq -r .result.operation_id)
# Poll for completion
until [ "$(curl -sS -H "$AUTH" \
  "$API/accounts/$CF_ACCOUNT_ID/rules/lists/bulk_operations/$OP" \
  | jq -r .result.status)" = "completed" ]; do sleep 2; done

# (c) Find or create the http_request_redirect entrypoint ruleset
RS=$(curl -sS -o /tmp/rs -w "%{http_code}" -H "$AUTH" \
  "$API/accounts/$CF_ACCOUNT_ID/rulesets/phases/http_request_redirect/entrypoint")
if [ "$RS" = "404" ]; then
  RULESET_ID=$(curl -sS -X POST -H "$AUTH" -H "$CT" \
    "$API/accounts/$CF_ACCOUNT_ID/rulesets" \
    -d '{"name":"DR redirects entrypoint","kind":"root","phase":"http_request_redirect","rules":[]}' \
    | jq -r .result.id)
else
  RULESET_ID=$(jq -r .result.id < /tmp/rs)
fi

# (d) Upsert the rule by ref. PUT the full rules array.
EXISTING=$(curl -sS -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rulesets/$RULESET_ID" \
  | jq --arg ref "$RULE_REF" '[.result.rules[] | select(.ref!=$ref)]')
NEW_RULE=$(jq -n --arg ref "$RULE_REF" --arg list "$LIST_NAME" '{
  ref:$ref, action:"redirect",
  expression:"http.request.full_uri in $"+$list,
  action_parameters:{from_list:{name:$list, key:"http.request.full_uri"}}
}')
RULES=$(jq -n --argjson e "$EXISTING" --argjson r "$NEW_RULE" '$e + [$r]')
curl -sS -X PUT -H "$AUTH" -H "$CT" \
  "$API/accounts/$CF_ACCOUNT_ID/rulesets/$RULESET_ID" \
  -d "$(jq -n --argjson rules "$RULES" '{rules:$rules}')" > /dev/null
```

Save the full script as `scripts/seo/apply-cloudflare-redirects.sh` and
commit it. Reruns are safe (lookup-by-name + PUT semantics).

### 1.3 Acceptance criteria

Run after deploy:

```sh
# Static row: returns 301 directly
curl -sSI https://dangerousrobot.org/claims \
  | grep -E '^(HTTP/2 301|location:|cf-ray:|server: cloudflare)$'
# Expected: HTTP/2 301; location: https://dangerousrobot.org/research/claims; cf-ray: <hex>-<POP>; server: cloudflare

# Wildcard row
curl -sSI https://dangerousrobot.org/claims/openai/corporate-structure \
  | grep -E '^(HTTP/2 301|location:)'
# Expected: location: https://dangerousrobot.org/research/claims/openai/corporate-structure

# A path NOT in the list should NOT be 301'd
curl -sSI https://dangerousrobot.org/values | grep -E '^HTTP/2'
# Expected: HTTP/2 200
```

A `HTTP/2 200` with a `<meta http-equiv="refresh">` body on `/claims`
means the rule is not active -- check the ruleset's `enabled` field and
the bulk-operation status.

---

## 2. Playbook refresh (file edit, agent-executable)

Edit `docs/seo-and-cloudflare-playbook.md` directly:

1. In the "Force initial indexing of key pages" list, replace pre-restructure
   paths with `/research/...` equivalents:
   - `/companies` -> `/research/companies`
   - `/products` -> `/research/products`
   - `/topics` -> `/research/topics`
   - `/claims` -> `/research/claims`
   - `/sources` -> `/research/sources`
   - `/criteria` -> `/research/criteria`
   - `/faq` -> `/research`
   - `/claims/openai/corporate-structure` -> `/research/claims/openai/corporate-structure`
   - `/entities/companies/openai` -> `/research/entities/companies/openai`
   - `/entities/products/chatgpt` -> `/research/entities/products/chatgpt`
2. Add to the same list:
   - `/research` (new hub)
   - `/resources` (new section hub)
   - `/resources/should-i`, `/resources/ai-safety`, `/resources/turn-off-ai`, `/resources/responsible-ai`
3. Under "Cloudflare dashboard -> Safe (apply now)", add:
   > 6. **Bulk Redirects:** the list `dr_redirects` and the entrypoint
   >    ruleset rule `dr_redirects_rule` consolidate the eight legacy
   >    section paths under `/research/...`. Maintained by
   >    `scripts/seo/apply-cloudflare-redirects.sh`.
4. In the "Alpha noindex policy" section, update the path examples from
   `/claims/{entity}/{claim}` to `/research/claims/{entity}/{claim}` (and
   similarly for sources / entities). The patterns in `src/lib/seo.ts`
   are already correct; this is just the prose.

### Acceptance: `grep -nE '^/(claims|entities|companies|products|subjects|topics|sources|criteria|faq)\b' docs/seo-and-cloudflare-playbook.md` returns no hits (zero false positives expected).

---

## 3. `/resources/*` structured data (code, agent-executable)

The four resource articles use distinct layouts. Each should carry JSON-LD
that matches what it actually is.

### 3.1 Schema mapping

| Slug | `layout` field | JSON-LD `@type` | Rationale |
|---|---|---|---|
| `should-i` | `tool` | `WebApplication` with `applicationCategory: UtilityApplication` | Decision tool that takes user input |
| `ai-safety` | (article) | `Article` with `about` -> `Thing { name: "FLI AI Safety Index" }` | Reference write-up |
| `turn-off-ai` | `guide` | `HowTo` with one `HowToSection` per platform; each section's `step` array is the steps for that platform | Canonical fit |
| `responsible-ai` | `matrix` | `Article` containing an embedded `ItemList` whose `itemListElement` mirrors the compared products | Comparison article |

All four also get: `headline` (from `title`), `description`, `datePublished`
(from `pubDate`), `dateModified` (max of any `last_verified` /
`last_checked` in `data`, else equal to `datePublished`), `author` ->
`Organization { name: "Dangerous Robot" }`, `publisher` -> same.

### 3.2 Implementation

1. Create `src/lib/resourceSchema.ts` exporting `buildResourceSchema(entry)`
   that switches on `entry.data.layout` and returns the right plain JS
   object. Keep it pure; no rendering.
2. In `src/pages/resources/[...slug].astro`, render the result via a
   `<script type="application/ld+json">` tag in the page head (similar to
   the `websiteSchema` block in `src/pages/index.astro`).
3. Read the four content files (`src/content/resources/{should-i,ai-safety,turn-off-ai,responsible-ai}.md`)
   to confirm each carries `title`, `description` (< 160 chars), and
   `pubDate`. If `description` is missing or too long, fix the
   frontmatter -- this is a tractable per-file edit.
4. Confirm the resources hub (`src/pages/resources/index.astro`) and the
   homepage have an internal link to the section.

### 3.3 Acceptance criteria

For each resource URL, after deploy:

```sh
# Each page emits exactly one application/ld+json block
for slug in should-i ai-safety turn-off-ai responsible-ai; do
  count=$(curl -sS https://dangerousrobot.org/resources/$slug \
    | grep -c 'application/ld+json')
  test "$count" -ge 1 || { echo "missing JSON-LD on $slug"; exit 1; }
done

# Validate at schema.org (HEAD-driven check; agent should also submit to
# https://validator.schema.org/ and capture screenshots if a browser is available)
```

Plus a manual run of <https://validator.schema.org/> on each URL -- 0
errors required. Warnings (e.g., recommended `image` field) are
acceptable for v1 but should be tracked in `docs/UNSCHEDULED.md`.

---

## 4. Internal link audit (grep + edit, agent-executable)

Any in-site href to a legacy path triggers the meta-refresh fallback (or,
after section 1, a Cloudflare 301 hop). Both are avoidable.

### 4.1 Recipe

```sh
# All source files: components, pages, layouts
rg -nE 'href="/(claims|entities|companies|products|subjects|topics|sources|criteria|faq)(/|"|#)' src/ \
  > /tmp/legacy-links-src.txt

# Markdown bodies for both research and resources content
rg -nE '\]\(/(claims|entities|companies|products|subjects|topics|sources|criteria|faq)(/|\)|#)' \
  research/ src/content/resources/ \
  > /tmp/legacy-links-md.txt

# Inspect both files. For each hit, change the path to /research/<rest>.
```

After fixes, re-run both `rg` commands. Both must return empty.

### 4.2 Acceptance criteria

```sh
test ! -s /tmp/legacy-links-src.txt
test ! -s /tmp/legacy-links-md.txt
```

Commit as a single `fix(seo): retarget legacy internal links` change.

---

## 5. GSC verification + watch

Split by automation surface. All operations run after sections 1-4 ship.

### 5.1 Sitemap submission (API, agent)

```sh
TOKEN=$(gcloud auth print-access-token)
SITE=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("sc-domain:dangerousrobot.org",safe=""))')
FEED=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("https://dangerousrobot.org/sitemap-index.xml",safe=""))')
curl -sS -X PUT -H "Authorization: Bearer $TOKEN" \
  "https://www.googleapis.com/webmasters/v3/sites/$SITE/sitemaps/$FEED"
# 200 OK + empty body on success
```

Acceptance: a follow-up `GET https://www.googleapis.com/webmasters/v3/sites/$SITE/sitemaps/$FEED`
returns the sitemap with `isPending: false` and `lastSubmitted` updated.

### 5.2 URL inspection sweep (API, agent)

For each URL in a target list (see below), call:

```sh
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://searchconsole.googleapis.com/v1/urlInspection/index:inspect \
  -d "{\"inspectionUrl\":\"$URL\",\"siteUrl\":\"sc-domain:dangerousrobot.org\",\"languageCode\":\"en-US\"}"
```

Store the JSON to `seo-runs/urlinspect-YYYY-MM-DD/<url-encoded>.json`.

Target list (script `scripts/seo/inspect-urls.sh`):

- Top-level: `/`, `/research`, `/resources`, `/values`, `/credits`
- Resource pages: `/resources/{should-i,ai-safety,turn-off-ai,responsible-ai}`
- Research index pages: `/research/{claims,companies,products,subjects,topics,sources,criteria}`
- Two representative legacy URLs (must show `coverageState` containing "redirect"):
  `/claims`, `/companies`

Acceptance per URL:

- `/research/*` indexes: `verdict: PASS`, `googleCanonical == userCanonical == <self>`, `robotsTxtState: ALLOWED`.
- `/resources/*`: same plus `indexingState != "BLOCKED_BY_META_TAG"`.
- Legacy URLs: `coverageState` matches `/redirect/i`, `googleCanonical` points to the `/research/...` target.

### 5.3 Request Indexing (browser, paced)

No public API. Drive search.google.com/search-console via the
Chrome MCP. Pseudocode (drive by visible text, never by class hash):

```
INPUT: queue file scripts/seo/request-indexing-queue.txt (one URL per line)
RATE:  10 URLs / day / property (Google's throttle)

navigate https://search.google.com/search-console?resource_id=sc-domain:dangerousrobot.org
for url in head -n 10 queue:
  focus  input[aria-label*="Inspect any URL"]
  type   url ; press Enter
  wait_for_text /URL is (on Google|not on Google)/ (timeout 90s)
  click  button: "Request Indexing"
  wait_for_text /Indexing requested|URL added to a priority crawl queue/ (timeout 120s)
  screenshot seo-runs/request-indexing-YYYY-MM-DD/<n>.png
  remove url from queue
  sleep 5
exit  # leave remaining URLs for tomorrow's run
```

Initial queue (in priority order): `/`, `/research`, `/resources`,
`/resources/should-i`, `/resources/ai-safety`, `/resources/turn-off-ai`,
`/resources/responsible-ai`, `/research/claims`, `/research/companies`,
`/research/products` -- exactly 10, fits one day.

Schedule for next day if more URLs accumulate.

Acceptance: per-URL screenshot showing the "Indexing requested" toast,
plus a re-run of section 5.2 for those URLs within 7 days showing
`coverageState` improving.

### 5.4 Coverage watch (browser, weekly)

The Pages / Coverage report has no API. Schedule a weekly browser run:

```
navigate https://search.google.com/search-console/index?resource_id=sc-domain:dangerousrobot.org
screenshot the four counts: "Not indexed -> Page with redirect",
                            "Not indexed -> Crawled - currently not indexed",
                            "Indexed",
                            "Not indexed -> Discovered - currently not indexed"
write seo-runs/coverage-YYYY-MM-DD.json with the four numbers
```

Expectations over weeks 1-4 after section 1 ships:

- "Page with redirect" count climbs as Google sees the new 301s; old
  legacy paths move into this bucket.
- "Indexed" count rises by ~5 (new hub + resources + their internal links).
- "Crawled - not indexed" should not spike. If it does, investigate the
  affected URLs in section 5.2.

If old URLs are still in "Indexed" after 4 weeks, re-verify section 1
(serve a real 301, not the Astro fallback) and re-submit via section 5.3.

---

## Risks / things to watch

- **HowTo rich results** have narrowed at Google over the last few years.
  If `turn-off-ai` doesn't earn them within a month, don't chase it --
  the structured data still aids entity understanding.
- **Cloudflare Bulk Redirects free-tier row limit** (currently 20). We're
  inside it; per-claim aliases later would push over. Switch to a Worker
  at that point.
- **Astro static refresh fallback pages** will be served if Cloudflare
  ever stops applying the rule (e.g. an accidental disable). Verify they
  carry `noindex` via `Base.astro` -- they should, but worth confirming.
- **GSC API quotas**: 2000 URL inspection requests/day/property is well
  above our list size. No risk today.
- **Browser-driven steps require a persisted, logged-in Chrome profile.**
  If the session expires, section 5.3 and 5.4 fail until a human
  re-authenticates. Plan for monthly re-auth.

## Sequencing

Each step has an "agent runnable: yes/no" tag. Order matters because the
verification steps depend on the redirect work landing first.

1. **Section 4** (internal-link audit) -- agent runnable: yes. Pure code,
   no infra dependency. Ship first.
2. **Section 3** (resources schema + meta) -- agent runnable: yes. Pure
   code, independent. Ship alongside 4.
3. **Section 1** (Cloudflare 301s) -- agent runnable: yes (REST). Needs
   prerequisite 0.1.
4. **Section 2** (playbook refresh) -- agent runnable: yes. Last, so it
   documents what was actually done.
5. **Section 5.1** (sitemap submit) -- agent runnable: yes. Needs 0.2.
6. **Section 5.2** (URL inspection sweep) -- agent runnable: yes. Run
   once now; schedule weekly thereafter.
7. **Section 5.3** (Request Indexing) -- agent runnable: yes via browser
   MCP. Needs 0.3.
8. **Section 5.4** (coverage watch) -- agent runnable: yes via browser
   MCP. Schedule weekly for 4 weeks, then monthly.

## Open questions

- Confirm the Astro meta-refresh fallback HTML pages carry `noindex`
  via `Base.astro`. If not, fix before section 1 ships (defense in
  depth).
- Verify `subjects` is listed in `astro.config.ts`'s redirect map. The
  plan list above includes it; the original commit should as well.

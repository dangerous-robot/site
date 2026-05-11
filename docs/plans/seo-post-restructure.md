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

- Permissions (all account-scope):
  - **Account** -> **Account Filter Lists** -> **Edit** (manages the redirect list)
  - **Account** -> **Account Rulesets** -> **Edit** (creates the http_request_redirect entrypoint ruleset rule)
  - **Account** -> **Bulk URL Redirects** -> **Edit** (authorizes attaching the list to the rules engine; some docs list this as "Mass URL Redirects")
- Account resources: include the account that owns `dangerousrobot.org`.
- No zone permissions needed.

Note: the dashboard permission dropdown is searchable. If "Bulk URL
Redirects" doesn't autocomplete, try "Mass URL Redirects" -- Cloudflare
renamed the product and the permission label varies by account.

Export for agent use:

```sh
export CF_API_TOKEN=...
export CF_ACCOUNT_ID=...   # from dash.cloudflare.com URL or accounts_list MCP tool
```

### 0.2 GSC auth (user OAuth via ADC)

**Important:** GSC's "Users and permissions" UI no longer accepts service
account emails -- it rejects them with "email not found." The
Site-Verification-API self-verify dance still works, but the simplest
path for a single-user project is **user OAuth via Application Default
Credentials**. The user (Brandon) is already a verified Owner of
`sc-domain:dangerousrobot.org`, so no additional access grants are
needed.

1. Make sure you have a GCP project that the Search Console API is
   enabled on (one-time). e.g. `dr-seo` (`dr-seo-496019`). Enable the
   API at <https://console.cloud.google.com/apis/library/searchconsole.googleapis.com?project=dr-seo-496019>.
2. Run the ADC login on a single line (no embedded newlines -- shell
   prompts that wrap input will split the command):

   ```sh
   gcloud auth application-default login --scopes='https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/webmasters,openid,https://www.googleapis.com/auth/userinfo.email' && gcloud auth application-default set-quota-project dr-seo-496019
   ```

   Browser opens, pick the Google account that owns the GSC property,
   click Allow. Credentials land in
   `~/.config/gcloud/application_default_credentials.json` with the
   `webmasters` scope.
3. Verify -- note the **mandatory** `x-goog-user-project` header (the
   legacy webmasters endpoint does not honor the ADC quota project
   without it):

   ```sh
   TOKEN=$(gcloud auth application-default print-access-token)
   curl -sS \
     -H "Authorization: Bearer $TOKEN" \
     -H "x-goog-user-project: dr-seo-496019" \
     "https://www.googleapis.com/webmasters/v3/sites" \
     | jq '.siteEntry[] | {url: .siteUrl, perm: .permissionLevel}'
   # Expect: sc-domain:dangerousrobot.org with perm "siteOwner"
   ```

Cache the GCP project ID for later snippets:

```sh
export GSC_QUOTA_PROJECT=dr-seo-496019
```

The access token is short-lived (~1h). All scripts should call
`gcloud auth application-default print-access-token` fresh per run, not
cache `$TOKEN` in a long-lived env var.

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
rows additionally set `subpath_matching: true` and inherit
`preserve_path_suffix: true` by default; the script sets it explicitly
for clarity. Static rows leave `subpath_matching` at its default `false`
and match only the exact path.

Note: literal `*` is not supported in `source_url`. The "wildcard"
behavior is the `subpath_matching: true` flag, which makes
`/claims/` match the entire subtree.

**Ordering matters.** Place the static (`subpath_matching: false`) rows
**before** the wildcard rows in `redirects.json`. Bulk Redirects evaluate
items top-down per request, so a wildcard listed first could shadow a
static row.

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

# Pre-flight: verify the token can see the account before any writes.
curl -sSf -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/tokens/verify" >/dev/null \
  || { echo "CF_API_TOKEN cannot access $CF_ACCOUNT_ID"; exit 1; }

# (a) Find or create the redirect list
LIST_ID=$(curl -sSf -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rules/lists" \
  | jq -r --arg n "$LIST_NAME" '.result[] | select(.name==$n and .kind=="redirect") | .id' | head -1)
if [ -z "$LIST_ID" ]; then
  LIST_ID=$(curl -sSf -X POST -H "$AUTH" -H "$CT" \
    "$API/accounts/$CF_ACCOUNT_ID/rules/lists" \
    -d '{"name":"'"$LIST_NAME"'","description":"dangerousrobot.org restructure 301s","kind":"redirect"}' \
    | jq -r .result.id)
fi
echo "LIST_ID=$LIST_ID"

# (b) Replace items in the list (PUT replaces; safe to rerun). Async op, poll with timeout + failure handling.
OP=$(curl -sSf -X PUT -H "$AUTH" -H "$CT" \
  "$API/accounts/$CF_ACCOUNT_ID/rules/lists/$LIST_ID/items" \
  --data @scripts/seo/redirects.json | jq -r .result.operation_id)
for _ in $(seq 1 60); do
  resp=$(curl -sSf -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rules/lists/bulk_operations/$OP")
  status=$(echo "$resp" | jq -r .result.status)
  case "$status" in
    completed) break ;;
    failed)    echo "$resp" | jq .result.error >&2; exit 1 ;;
    pending|running) sleep 2 ;;
    *) echo "unexpected bulk_op status: $status" >&2; exit 1 ;;
  esac
done
[ "$status" = "completed" ] || { echo "bulk_op timed out"; exit 1; }

# (c) Find or create the http_request_redirect entrypoint ruleset.
# Use -w with a newline so we can split body/status safely.
HTTP=$(curl -sS -o /tmp/rs.json -w '%{http_code}' -H "$AUTH" \
  "$API/accounts/$CF_ACCOUNT_ID/rulesets/phases/http_request_redirect/entrypoint")
if [ "$HTTP" = "200" ]; then
  RULESET_ID=$(jq -r .result.id < /tmp/rs.json)
elif [ "$HTTP" = "404" ]; then
  RULESET_ID=$(curl -sSf -X POST -H "$AUTH" -H "$CT" \
    "$API/accounts/$CF_ACCOUNT_ID/rulesets" \
    -d '{"name":"DR redirects entrypoint","kind":"root","phase":"http_request_redirect","rules":[]}' \
    | jq -r .result.id)
else
  echo "Unexpected status $HTTP from entrypoint GET" >&2; cat /tmp/rs.json >&2; exit 1
fi

# (d) Upsert the rule by ref. PUT the full rules array.
# Guard against null `rules` on a freshly-created ruleset.
EXISTING=$(curl -sSf -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rulesets/$RULESET_ID" \
  | jq --arg ref "$RULE_REF" '[(.result.rules // [])[] | select(.ref!=$ref)]')
NEW_RULE=$(jq -n --arg ref "$RULE_REF" --arg list "$LIST_NAME" '{
  ref: $ref,
  enabled: true,
  action: "redirect",
  description: "DR restructure 301s (list: \($list))",
  expression: "http.request.full_uri in $\($list)",
  action_parameters: { from_list: { name: $list, key: "http.request.full_uri" } }
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
# Static row: 301 with the correct Location, served by Cloudflare.
hdrs=$(curl -sSI https://dangerousrobot.org/claims)
echo "$hdrs" | grep -qiE '^HTTP/2 301'                                               || { echo "not 301"; exit 1; }
echo "$hdrs" | grep -qiE '^location: https://dangerousrobot\.org/research/claims\s*$' || { echo "wrong Location"; exit 1; }
echo "$hdrs" | grep -qiE '^(server|cf-ray):'                                          || { echo "not from Cloudflare edge"; exit 1; }

# Wildcard row preserves the suffix.
curl -sSI https://dangerousrobot.org/claims/openai/corporate-structure \
  | grep -qiE '^location: https://dangerousrobot\.org/research/claims/openai/corporate-structure'

# Path NOT in the list is unaffected.
curl -sSI https://dangerousrobot.org/values | grep -qiE '^HTTP/2 200'

# Loop protection: the target itself must not 301.
curl -sSI https://dangerousrobot.org/research/claims | grep -qiE '^HTTP/2 200'
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

5. Update the "Alpha noindex policy" example list (~lines 134-135 in
   the current playbook) which still enumerates the pre-restructure
   list pages. Apply the same `/research/...` replacements.

### Acceptance:

```sh
rg -n '\b/(claims|entities|companies|products|subjects|topics|sources|criteria|faq)\b' \
   docs/seo-and-cloudflare-playbook.md \
   | rg -v '/research/' \
   | { ! grep . ; }   # empty -> exit 0
```

The bare paths appear in backticks and prose; the inner `rg -v` filters
out the new `/research/...` references that legitimately contain those
substrings. Zero hits required.

---

## 3. `/resources/*` structured data (code, agent-executable)

**Current state**: `src/pages/resources/[...slug].astro` (lines 26-52)
already injects a generic `Article` JSON-LD for all four pages, with
`datePublished` from `pubDate` and a guide-specific `dateModified` from
`last_verified`. `src/layouts/Base.astro` (line ~117) additionally
injects an `Organization` schema on every page. So every resource URL
already ships at least two `application/ld+json` blocks.

This section **replaces** the generic Article block with a
layout-driven schema that better matches each page's actual content.
Organization stays as-is in `Base.astro`.

### 3.1 Schema mapping

Discriminator is the frontmatter `layout` field on each
`src/content/resources/*.md` file (verified 2026-05-11):

| Slug | `layout` field | JSON-LD `@type` | Rationale |
|---|---|---|---|
| `should-i` | `tool` | `WebApplication` with `applicationCategory: "BusinessApplication"` (a valid Schema.org enum; `UtilityApplication` is not), plus `browserRequirements: "Requires JavaScript"` | Decision tool that takes user input |
| `ai-safety` | `article` | `Article` with `about` -> `Thing { name: "FLI AI Safety Index" }` | Reference write-up |
| `turn-off-ai` | `guide` | `HowTo` with one `HowToSection` per platform; each section's `itemListElement` (or `step`) is the steps for that platform | Canonical fit |
| `responsible-ai` | `matrix` | `Article` containing an embedded `ItemList` whose `itemListElement` mirrors the compared products | Comparison article |

All four also get: `headline` (from `title`), `description`, `datePublished`
(from `pubDate`), `dateModified` (max of any `last_verified` /
`last_checked` in `data`, else equal to `datePublished`), `author` ->
`Organization { name: "Dangerous Robot" }`, `publisher` -> same.

### 3.2 Implementation

1. Create `src/lib/resourceSchema.ts` exporting `buildResourceSchema(entry)`
   that switches on `entry.data.layout` and returns the right plain JS
   object. Keep it pure; no rendering.
2. In `src/pages/resources/[...slug].astro`, **replace** the existing
   generic `articleSchema` block (currently around lines 26-52, ending
   at the closing `</script>` of `application/ld+json`) with a call to
   `buildResourceSchema(entry)` and the same `<script type="application/ld+json">`
   wrapper.
3. Read the four content files (`src/content/resources/{should-i,ai-safety,turn-off-ai,responsible-ai}.md`)
   to confirm each carries `title`, `description` (< 160 chars), and
   `pubDate`. If `description` is missing or too long, fix the
   frontmatter -- this is a tractable per-file edit.
4. Confirm the resources hub (`src/pages/resources/index.astro`) and the
   homepage have an internal link to the section.

### 3.3 Acceptance criteria

For each resource URL, after deploy:

```sh
# Each page emits Organization (from Base.astro) + the per-layout block: >=2 expected.
for slug in should-i ai-safety turn-off-ai responsible-ai; do
  count=$(curl -sS https://dangerousrobot.org/resources/$slug \
    | grep -c 'application/ld+json')
  test "$count" -ge 2 || { echo "$slug has $count ld+json blocks (expected >=2)"; exit 1; }
done

# Smoke-test the per-layout @type appears (catches a regression where
# the generic Article block is left in place).
curl -sS https://dangerousrobot.org/resources/turn-off-ai | grep -q '"@type":"HowTo"'      || { echo "turn-off-ai missing HowTo"; exit 1; }
curl -sS https://dangerousrobot.org/resources/should-i    | grep -q '"@type":"WebApplication"' || { echo "should-i missing WebApplication"; exit 1; }
```

Plus a manual run of <https://validator.schema.org/> on each URL (or the
Chrome MCP equivalent), capturing the result. 0 errors required;
warnings (e.g. recommended `image` field) acceptable for v1 but should
be tracked in `docs/UNSCHEDULED.md`.

---

## 4. Internal link audit (verification step, agent-executable)

Any in-site href to a legacy path triggers the meta-refresh fallback
(or, after section 1, a Cloudflare 301 hop). Both are avoidable.

**Current state (verified 2026-05-11)**: both greps below return empty.
This section is now a regression-prevention check, not a corrective
edit. Keep it; run it as part of the section-5 verification sweep.

### 4.1 Recipe

```sh
# Astro source: catches both href="/..." and href={"/..."} (and similar
# bracket/quote variants). Excludes the redirect map itself and any
# legitimate /research/... references.
rg -nE '/(claims|entities|companies|products|subjects|topics|sources|criteria|faq)(/|[\`"'"'"'\}#?])' src/ \
  | rg -v 'astro\.config\.ts|/research/' \
  > /tmp/legacy-links-src.txt

# Markdown bodies for both research and resources content
rg -nE '\]\(/(claims|entities|companies|products|subjects|topics|sources|criteria|faq)(/|[)#?])' \
  research/ src/content/resources/ \
  > /tmp/legacy-links-md.txt

# Both files must be empty. If either has hits, rewrite the path to /research/<rest>.
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

All API calls auth via ADC (set up in section 0.2) and **must** include
`x-goog-user-project: $GSC_QUOTA_PROJECT` -- the legacy webmasters
endpoint returns 403 without it.

### 5.1 Sitemap submission (API, agent)

```sh
TOKEN=$(gcloud auth application-default print-access-token)
SITE=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("sc-domain:dangerousrobot.org",safe=""))')
FEED=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("https://dangerousrobot.org/sitemap-index.xml",safe=""))')
HTTP=$(curl -sS -o /dev/null -w '%{http_code}' -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "x-goog-user-project: $GSC_QUOTA_PROJECT" \
  "https://www.googleapis.com/webmasters/v3/sites/$SITE/sitemaps/$FEED")
case "$HTTP" in 2*) ;; *) echo "sitemap submit failed: $HTTP"; exit 1 ;; esac
# Empty body; success is any 2xx (Google returns 204 in practice).
```

Acceptance: a follow-up `GET https://www.googleapis.com/webmasters/v3/sites/$SITE/sitemaps/$FEED`
(same two headers) returns the sitemap with `isPending: false` and
`lastSubmitted` updated.

### 5.2 URL inspection sweep (API, agent)

For each URL in a target list (see below), call:

```sh
TOKEN=$(gcloud auth application-default print-access-token)
curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "x-goog-user-project: $GSC_QUOTA_PROJECT" \
  -H "Content-Type: application/json" \
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

Acceptance per URL. Fields live under
`.inspectionResult.indexStatusResult` in the response -- they are NOT
at the top level. Example jq pluck:

```sh
jq '.inspectionResult.indexStatusResult |
    {verdict, coverageState, googleCanonical, userCanonical, robotsTxtState, indexingState}'
```

- `/research/*` indexes: `verdict == "PASS"`, `googleCanonical == userCanonical == <self>`, `robotsTxtState == "ALLOWED"`, `indexingState == "INDEXING_ALLOWED"`.
- `/resources/*`: same; `indexingState` must NOT be `"BLOCKED_BY_META_TAG"`.
- Legacy URLs: `coverageState` matches `/redirect/i` (free-form string,
  e.g. `"Page with redirect"`); `googleCanonical` points to the
  `/research/...` target.

To stay clear of the 600 QPM/site bucket, sleep ~150ms between calls in
the sweep script (the daily 2000 QPD ceiling is well above our ~20 URL
list).

### 5.3 Request Indexing (browser, paced)

No public API. The Google Indexing API is restricted to `JobPosting` /
`BroadcastEvent` and does NOT apply here. Drive
search.google.com/search-console via the Chrome MCP. Pseudocode (drive
by visible text, never by class hash):

GSC's UI strings drift; on first run the agent must capture the current
labels rather than trusting the patterns below:

1. After navigating, call `get_page_text` and save to
   `seo-runs/gsc-ui-fingerprint-YYYY-MM-DD.txt`.
2. Locate the inspect box (try `aria-label /Inspect any URL/i`, then
   `placeholder /Inspect/i`, then any top-of-page `<input>`).
3. After clicking **Request Indexing**, capture the toast text verbatim
   and update the wait-for-text pattern in this plan.

```
INPUT: queue file scripts/seo/request-indexing-queue.txt (one URL per line)
RATE:  Google throttles Request Indexing without publishing a number;
       observed cap is ~10-12/day/property. Stop early if the button
       is disabled or the toast matches /quota|rate|try again/i.

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

The Pages / Coverage report has no API. The Search Console API only
exposes Sites, Sitemaps, URL Inspection, and Search Analytics; the
Pages buckets ("Page with redirect", "Crawled - currently not indexed",
"Discovered - currently not indexed") are UI-only. For an API-only
approximation between weekly screenshots, diff the sitemap URL list
against the URL-inspection results from section 5.2: any sitemap URL
whose `coverageState` is non-empty and doesn't start with `"Submitted
and indexed"` is a candidate "not indexed" entry. Treat the screenshots
as the source of truth for counts.

Schedule a weekly browser run:

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
- **Cloudflare Bulk Redirects free-tier quota** (20 redirects per
  account on the free plan, bundled with one ruleset rule slot in the
  http_request_redirect phase). We use 13. Per-claim aliases later
  would push over; switch to a Cloudflare Worker (or Transform Rule)
  at that point. See
  <https://developers.cloudflare.com/rules/url-forwarding/bulk-redirects/#availability>.
- **Astro static refresh fallback pages** ship `<meta name="robots"
  content="noindex">` and the correct `<link rel="canonical">` already
  (emitted by Astro's `core/routing/3xx.js` for every entry in
  `astro.config.ts`'s `redirects` map). Confirmed in `dist/` on
  2026-05-11; no change needed.
- **GSC API quotas** (per <https://developers.google.com/webmaster-tools/limits>):
  2000 queries/day/site and 600 queries/minute/site for URL Inspection;
  10M/day and 15M/minute per GCP project. Our target list is ~20 URLs,
  well under both. Sleep ~150ms between calls if the list ever grows.
- **GCP quota project lapse.** If `dr-seo-496019` is suspended/deleted
  or its billing is removed, every GSC call returns 403
  `PERMISSION_DENIED` with a message mentioning the project. The fix is
  to re-enable the Search Console API on that project, or point
  `GSC_QUOTA_PROJECT` at a different enabled project the user has
  access to. Re-running `print-access-token` does NOT help.
- **ADC scope drift.** Plain `gcloud auth application-default login`
  (no `--scopes`) overwrites credentials with cloud-platform-only and
  drops the `webmasters` scope. Symptom: 403 `insufficientPermissions`
  with no project mention. Fix: re-run the exact section-0.2 command.
- **Browser-driven steps require a persisted, logged-in Chrome profile.**
  If the session expires, section 5.3 and 5.4 fail until a human
  re-authenticates. Plan for monthly re-auth.
- **ADC refresh token longevity.** The OAuth refresh token from section
  0.2 lives indefinitely under normal use but can be invalidated by:
  prolonged inactivity (>6 months), password change, or revocation in
  the Google Account "Connected apps" view. If `print-access-token`
  starts returning errors, re-run the section-0.2 login command.
- **GSC UI rejects service account emails.** Documented here so the next
  reader doesn't waste a cycle re-trying. "Users and permissions -> Add
  user" returns "email not found" for any `*.iam.gserviceaccount.com`
  address. The two working paths for headless GSC access are user-OAuth
  (what we use) and the Site Verification API self-verify dance with a
  DNS TXT record.

## Sequencing

Each step has an "agent runnable: yes/no" tag. Order matters because the
verification steps depend on the redirect work landing first.

1. **Section 4** (internal-link audit) -- agent runnable: yes. Pure
   verification today (both greps return empty); rerun as part of the
   pre-deploy check for sections 1 and 3.
2. **Section 3** (resources JSON-LD replacement) -- agent runnable:
   yes. Pure code, independent. Ship before 5.3 so the requested
   indexing pulls the right schema.
3. **Section 1** (Cloudflare 301s) -- agent runnable: yes (REST). Needs
   prerequisite 0.1. Independent of 3/4; can ship in parallel.
4. **Section 2** (playbook refresh) -- agent runnable: yes. After 1+3+4
   so it documents what actually shipped.
5. **Section 5.1** (sitemap submit) -- agent runnable: yes. Idempotent;
   can run any time after 0.2, but most useful after 3+4 so Google's
   first crawl sees the new schema.
6. **Section 5.2** (URL inspection sweep) -- agent runnable: yes. Run
   once after 1+3 ship; schedule weekly for the next 4 weeks.
7. **Section 5.3** (Request Indexing) -- agent runnable: yes via browser
   MCP. Needs 0.3 and depends on 3 shipping (so the right schema gets
   indexed on first crawl).
8. **Section 5.4** (coverage watch) -- agent runnable: yes via browser
   MCP. Schedule weekly for 4 weeks, then monthly.

## 6. Carry-over backlog

These are surfaced by the restructure but not in scope for this plan.
File them in `docs/UNSCHEDULED.md` rather than expanding scope here.

- **OG image** for share previews. `dr-logo.png` is square; Twitter/FB
  want 1200x630. The playbook already flags this. After the restructure
  the new `/research/` and `/resources/*` URLs inherit the same default,
  so share-card quality is uniformly low. One properly-sized image
  passed via `ogImage` from `Base.astro` (or per-section) is the v1
  upgrade.
- **robots.txt sanity check** post-deploy:
  ```sh
  curl -sS https://dangerousrobot.org/robots.txt
  # Expect: Allow: /  +  Sitemap: https://dangerousrobot.org/sitemap-index.xml
  ```
  Not gating; just a one-liner to add to the section-5 verification
  script.

## Open questions

All previously-listed questions are now resolved:

- **Astro fallback noindex**: verified 2026-05-11 -- Astro's
  `core/routing/3xx.js` emits `<meta name="robots" content="noindex">`
  and the correct canonical on every meta-refresh page in `dist/`.
- **`subjects` redirect**: `astro.config.ts` has the static
  `/subjects -> /research/subjects` row. No wildcard is needed because
  there's no `/pages/subjects/[...slug]` route (`/research/subjects` is
  index-only). The plan's redirect table matches reality.

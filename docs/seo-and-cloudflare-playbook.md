# SEO & Cloudflare playbook: dangerousrobot.org

A short checklist for ongoing work in Google Search Console (GSC) and the
Cloudflare dashboard. Last reviewed: 2026-10-09.

What to do next, in order, is in [`plans/seo-external.md`](plans/seo-external.md)
§ "Do now". This file holds the how-to steps.

## Google Search Console

### One-time setup (done)

1. Open <https://search.google.com/search-console>.
2. Property: **Domain** `dangerousrobot.org` (`sc-domain:dangerousrobot.org`),
   verified via the DNS TXT record in Cloudflare. Domain verification covers
   apex, www, and any future subdomain.
3. Settings → Users and permissions: add backup owners if relevant.

### Submit sitemap (done; resubmit after the indexing flip)

1. **Sitemaps** → enter `sitemap-index.xml` → Submit, or run
   `scripts/seo/submit-sitemap.sh` (needs `GSC_QUOTA_PROJECT` exported and a
   gcloud application-default login).
   (Do NOT submit `sitemap.xml`: that path 404s. The index covers the same
   URLs.)
2. Wait 24–72 hours for Google to fetch and report status.

### Force initial indexing of key pages

For each URL Google has not indexed: **URL Inspection → Test live URL →
Request Indexing**. Check first with `scripts/seo/inspect-urls.sh` or URL
Inspection; skip pages already indexed. Every URL below except `/` currently
301s to its trailing-slash form while the canonical tag and sitemap use the
no-slash form; the fix is SITE-Z (Trailing-slash URLs) in the roadmap.
Request indexing after it lands. In priority order:

1. `/resources/responsible-ai` (the page SITE-J, Responsible AI chatbots, is building)
2. `/resources`, `/resources/ai-safety`, `/resources/should-i`,
   `/resources/turn-off-ai`, `/resources/ai-safety-winter-2025`
3. `/` (homepage), `/writing`, `/writing/why-dangerous-robot-exists`,
   `/petitions/prohibit-ai-self-improvement`, `/about`
4. `/research` (research hub), `/research/criteria`, `/research/topics`,
   `/research/claims`, `/research/companies`, `/research/products`,
   `/research/subjects`, `/research/sources`

Do not request indexing for claim, source or entity pages until the indexing
flip (see "Pre-release noindex policy"), including the subject claim pages
that are indexable today by mistake.

`scripts/seo/request-indexing-queue.txt` holds an older 10-URL queue in a
different order; use the list above.

Google rate-limits Request Indexing to ~10/day per property; pace accordingly.

### Recurring checks

Cadence and action thresholds: [`plans/seo-external.md`](plans/seo-external.md)
§ "Monitoring and maintenance" (monthly, inbound links quarterly). Where to
look in GSC:

- **Pages report:** "Why pages aren't indexed." What each bucket means is
  in the plan's "What to watch for".
- **Sitemaps:** `sitemap-index.xml` is **Success**, with the discovered URL
  count close to the number of `<loc>` entries in the live `sitemap-0.xml`.
- **Experience → Core Web Vitals:** Mobile and Desktop.
- **Enhancements:** structured-data items with zero errors.
- **Security & Manual actions:** should be empty.
- **Performance:** Queries, to see what Google shows the site for.

Save each check's evidence in `seo-runs/` (git-ignored, local only), as the
plan's "Do now" table describes.

### Submit a change of address only if needed

You don't have one. Skip.

### Verifying the 404 page after a change

After a deploy that changes `404.astro`, in **URL Inspection** test a URL
you know doesn't exist (e.g. `/__not-a-real-page`). Live test should return
HTTP 404 and the page preview should show the branded 404, not the GitHub
Pages default.

---

## Cloudflare dashboard

In `dash.cloudflare.com` → select `dangerousrobot.org`.

### Behavior in place (curl, 2026-10-09)

Which dashboard setting produces each behavior is unverified.

1. **SSL/TLS → Edge Certificates → Always Use HTTPS:** on.
   `http://dangerousrobot.org/` returns 301 to HTTPS.
2. **Transform Rules → Modify Response Header:** responses carry
   `X-Content-Type-Options: nosniff`,
   `Referrer-Policy: strict-origin-when-cross-origin` and
   `Permissions-Policy: interest-cohort=(), browsing-topics=()`.
3. **HSTS:** responses carry
   `Strict-Transport-Security: max-age=31536000; includeSubDomains` (no
   preload). Do not enable preload until you're certain the apex and every
   current and future subdomain will stay on HTTPS forever; preload is hard
   to undo.
4. **www → apex:** `https://www.dangerousrobot.org/` returns 301 to
   `https://dangerousrobot.org/`.
5. **Bulk Redirects:** the list `dr_redirects` and the entrypoint ruleset rule
   `dr_redirects_rule` send the legacy section paths (`/faq`, `/claims`,
   `/companies` and others) to `/research/...`. Maintained by
   `scripts/seo/apply-cloudflare-redirects.sh` from
   `scripts/seo/redirects.json`.

### To confirm in the dashboard (unverified)

1. **SSL/TLS → Overview:** encryption mode is **Full**, not **Flexible**.
   GitHub Pages serves valid TLS, so Full is safe.
2. **DNS:** the `www` record is a CNAME to `dangerousrobot.org` and proxied
   (orange cloud).
3. **Speed → Optimization:** Brotli is on. (Cloudflare retired Auto Minify
   in 2024; if the dashboard no longer shows it, skip that part.)

### Ask before flipping

1. **Bot Fight Mode** (Security → Bots): default is fine for a static site,
   but it can occasionally block legitimate RSS/feed readers. Enable only if
   you see actual bot abuse.
2. **Rate Limiting Rules:** none needed for the static site today. The
   petition Worker throttles in code (`workers/api/wrangler.toml`); an edge
   rule for it is a security item, not an SEO one.

### Skip / not applicable

- **Email Address Obfuscation:** site doesn't expose emails.
- **Hotlink Protection:** no images worth protecting.
- **Argo Smart Routing / Tiered Cache:** paid; static GitHub Pages origin
  doesn't benefit much.
- **Cache Rules:** the Astro output already sets `Cache-Control` via
  GitHub Pages defaults; revisit only if PageSpeed Insights flags it.

### Deferred

- **Content-Security-Policy:** non-trivial because of inline scripts. Worth
  doing carefully later, not as a one-line edit.
- **OG image at 1200×630:** open, not deferred; tracked in
  `docs/UNSCHEDULED.md` ("SEO post-restructure follow-ups", the wide default
  share image row). The default `og:image` is `/dr-logo-light-bg.png`
  (512×512, square) with `twitter:card` set to `summary_large_image`. Only
  writing posts and petitions with an `image` field get a 1200px-wide share
  image (`src/lib/share-image.ts`). Do it once a wide image exists.

---

## Pre-release noindex policy

Detail pages under `/research/claims/{entity}/{claim}`,
`/research/sources/{yyyy}/{slug}`, and `/research/entities/{type}/{slug}` are
generated from AI agent research. Until the indexing flip below they are:

1. Served with `<meta name="robots" content="noindex,nofollow">`.
2. Excluded from `sitemap-index.xml` / `sitemap-0.xml`.

**Known gap:** subject claim pages, `/research/claims/subjects/{subject}/{claim}`,
are not covered. The claim pattern in `src/lib/seo.ts:35` matches two path
segments after `/research/claims/`; subject claims have three. Checked live
2026-10-09: they serve `index,follow` and are in `sitemap-0.xml`. A code fix
is needed; until then, do not request indexing for them.

URLs are stable: already-published pages remain accessible at the same paths.
Internal navigation, deep links, and direct visits all still work; the pages
are just hidden from search engines.

Every other page remains indexable: `/`, `/resources` and its five guides,
`/research` and its list pages (`/research/claims`, `/research/companies`,
`/research/products`, `/research/subjects`, `/research/sources`,
`/research/topics`, `/research/criteria`), `/research/topics/*`,
`/research/criteria/*`, `/writing` and its posts, `/petitions/*`, `/about`,
`/values`, `/corrections`, `/credits`, `/privacy`, `/people/*`. A resource
page can opt out with `noindex: true` in its frontmatter; none does today.

### When the pre-release noindex period ends

The flip happens after 1.0.0; Brandon decides the trigger
(`docs/decisions.md:19`). The flag name keeps its historical `ALPHA` spelling.

To re-enable indexing of detail pages:

1. Open `src/lib/seo.ts`.
2. Change `INDEX_ALPHA_DETAIL_PAGES` from `false` to `true`.
3. Commit, build, and deploy.
4. In GSC, resubmit the sitemap (Sitemaps → Submit `sitemap-index.xml`, or
   `scripts/seo/submit-sitemap.sh`) so Google sees the newly-included URLs
   sooner.
5. Spot-check a few previously-noindexed URLs in GSC URL Inspection to confirm
   they no longer carry the noindex directive.
6. Run the validation milestone in [`plans/seo-external.md`](plans/seo-external.md)
   on a claim page and an entity page.

## What was already done in the repo

- `src/layouts/Base.astro`: `meta robots`, `theme-color`, `og:site_name`,
  `og:locale`, `og:image:alt`, full Twitter Card tags, `Organization` JSON-LD,
  and a `noindex` prop.
- `src/pages/404.astro`: branded 404 page with `noindex`, replacing the
  GitHub Pages default.
- `src/lib/seo.ts`: pre-release indexing flag (`INDEX_ALPHA_DETAIL_PAGES`) and path classifier.
- `src/pages/research/{claims,sources,entities}/[...slug].astro`: pass
  `noindex={shouldNoindex(...)}` to `Base`.
- `astro.config.ts`: sitemap `filter` excludes pre-release detail paths.

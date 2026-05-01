# SEO & Cloudflare playbook — dangerousrobot.org

A short checklist for ongoing work in Google Search Console (GSC) and the
Cloudflare dashboard. Companion to the audit done on 2026-04-30.

## Google Search Console

### One-time setup

1. Open <https://search.google.com/search-console>.
2. If `dangerousrobot.org` isn't listed, **Add property → Domain**, enter
   `dangerousrobot.org`, and verify via the DNS TXT record in Cloudflare.
   (Domain verification covers apex, www, and any future subdomain — preferred
   over URL-prefix.)
3. Settings → Users and permissions: add backup owners if relevant.

### Submit sitemap

1. **Sitemaps** → enter `sitemap-index.xml` → Submit.
   (Do NOT submit `sitemap.xml` — that path 404s. The index covers the same
   URLs.)
2. Wait 24–72 hours for Google to fetch and report status.

### Force initial indexing of key pages

For each of these URLs: **URL Inspection → Test live URL → Request Indexing**.

- `/` (homepage)
- `/companies`, `/products`, `/topics`, `/claims`, `/sources`, `/criteria`,
  `/faq`
- 2–3 representative claim pages, e.g. `/claims/openai/corporate-structure`
- 2–3 entity pages, e.g. `/entities/companies/openai`,
  `/entities/products/chatgpt`

Google rate-limits Request Indexing to ~10/day per property — pace accordingly.

### Recurring checks (weekly for the first month, then monthly)

- **Pages report:** look at "Why pages aren't indexed."
  - "Discovered – currently not indexed": needs time + external links.
  - "Crawled – currently not indexed": Google saw it but skipped — usually
    thin/duplicate content. Check the affected pages.
  - "Soft 404": should drop to zero once the new `404.astro` is deployed.
  - "Server error (5xx)" or "Redirect error": investigate immediately.
- **Sitemaps:** confirm `sitemap-index.xml` is **Success**, with the discovered
  URL count matching your repo (today: 74).
- **Experience → Core Web Vitals:** check both Mobile and Desktop. Aim for all
  URLs in **Good**. The site is animation-heavy on the homepage; LCP and CLS
  are the ones to watch.
- **Enhancements:** confirm the structured-data items (Organization, WebSite)
  show as **Valid** with zero errors.
- **Manual actions / Security issues:** should be empty. Investigate
  immediately if not.
- **Performance:** once data accrues (~1 week), look at Queries to see what
  Google is showing the site for. Helpful for content gaps.

### Submit a change of address only if needed

You don't have one. Skip.

### Verifying the new 404 page after deploy

After the next deploy, in **URL Inspection** test a URL you know doesn't
exist (e.g. `/__not-a-real-page`). Live test should return HTTP 404 and the
page preview should show the branded 404, not the GitHub Pages default.

---

## Cloudflare dashboard

In `dash.cloudflare.com` → select `dangerousrobot.org`.

### Safe (apply now)

1. **SSL/TLS → Edge Certificates → Always Use HTTPS:** ON.
   (Currently `http://dangerousrobot.org` returns 200 over plain HTTP.)
2. **SSL/TLS → Overview:** confirm encryption mode is **Full**, not
   **Flexible**. GitHub Pages serves valid TLS, so Full is safe.
3. **Rules → Transform Rules → Modify Response Header → Create rule
   ("All incoming requests"):**
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Permissions-Policy: interest-cohort=(), browsing-topics=()`
4. **DNS:** confirm a CNAME record `www → dangerousrobot.org` exists and
   is proxied (orange cloud). The 301 from `www` to apex is already working;
   this is just verifying how.
5. **Speed → Optimization:** verify Brotli is on; Auto Minify (HTML) is fine
   for static Astro output.

### Ask before flipping

1. **HSTS** (SSL/TLS → Edge Certificates → HSTS):
   `max-age=31536000; includeSubDomains`. **Do not enable preload** until
   you're certain the apex + every current and future subdomain will stay on
   HTTPS forever — preload is hard to undo.
2. **Bot Fight Mode** (Security → Bots): default is fine for a static site,
   but it can occasionally block legitimate RSS/feed readers. Enable only if
   you see actual bot abuse.
3. **Rate Limiting Rules:** none needed today. Add only if you see abuse in
   Analytics.

### Skip / not applicable

- **Email Address Obfuscation:** site doesn't expose emails.
- **Hotlink Protection:** no images worth protecting.
- **Argo Smart Routing / Tiered Cache:** paid; static GitHub Pages origin
  doesn't benefit much.
- **Cache Rules:** the Astro output already sets `Cache-Control` via
  GitHub Pages defaults; revisit only if Page Speed Insights flags it.

### Deferred

- **Content-Security-Policy:** non-trivial because of inline scripts and
  Google Fonts. Worth doing carefully later, not as a one-line edit.
- **OG image at 1200×630:** the current `dr-logo.png` is square. Generate a
  proper social-card image and pass it via the `ogImage` prop in `Base.astro`
  for top-level pages.

---

## Alpha noindex policy

Detail pages under `/claims/{entity}/{claim}`, `/sources/{yyyy}/{slug}`, and
`/entities/{type}/{slug}` are generated from AI agent research. While the site
is in alpha they are:

1. Served with `<meta name="robots" content="noindex,nofollow">`.
2. Excluded from `sitemap-index.xml` / `sitemap-0.xml`.

URLs are stable — already-published pages remain accessible at the same paths.
Internal navigation, deep links, and direct visits all still work; the pages
are just hidden from search engines.

List/index pages (`/`, `/claims`, `/companies`, `/products`, `/sources`,
`/topics`, `/criteria`, `/faq`, `/values`, `/credits`) remain indexable.

### When alpha ends

To re-enable indexing of detail pages:

1. Open `src/lib/seo.ts`.
2. Change `INDEX_ALPHA_DETAIL_PAGES` from `false` to `true`.
3. Commit, build, and deploy.
4. In GSC, resubmit the sitemap (Sitemaps → Submit `sitemap-index.xml`) so
   Google sees the newly-included URLs sooner.
5. Spot-check a few previously-noindexed URLs in GSC URL Inspection to confirm
   they no longer carry the noindex directive.

Already-indexed pages that fall under the alpha rules (homepage and entity
detail pages crawled before this change) will be removed from Google's index
within roughly 1–2 weeks as Googlebot recrawls and sees the noindex tag. No
action needed.

## What was already done in the repo

- `src/layouts/Base.astro`: added `meta robots`, `theme-color`, `og:site_name`,
  `og:locale`, `og:image:alt`, full Twitter Card tags, and a `noindex` prop.
- `src/pages/404.astro`: branded 404 page with `noindex`, replacing the
  GitHub Pages default.
- `src/lib/seo.ts`: alpha indexing flag and path classifier.
- `src/pages/{claims,sources,entities}/[...slug].astro`: pass
  `noindex={shouldNoindex(...)}` to `Base`.
- `astro.config.ts`: sitemap `filter` excludes alpha detail paths.

# Plan: external SEO — dangerousrobot.org

| Milestone | Status |
|-----------|--------|
| Search console setup | `[ ] ready — pending launch` |
| Google Fact Check program | `[ ] gated — prereqs not met` |
| Validation and testing | `[ ] gated — code plan must land first` |
| Link building and citation outreach | `[ ] ongoing — start at launch` |
| Monitoring and maintenance | `[ ] ongoing — start after indexing` |

---

## Background

This plan covers external platform registrations, submissions, validations, and monitoring tasks. Nothing here requires code changes to the site. The companion code-side SEO work (sitemap, JSON-LD schemas, meta tags, font loading) is tracked separately; several milestones here are gated on that work landing first.

Domain: `dangerousrobot.org` (bare domain, no www). Confirmed via `public/CNAME`. The GitHub README links to the live site at `https://dangerousrobot.org`.

---

## Milestone: Search console setup

**Status:** `[ ] ready — pending launch`

**Gating condition:** Site must be publicly accessible at `dangerousrobot.org`. Alpha is fine; the site does not need to be post-launch.

### 1. Google Search Console (GSC)

**URL:** https://search.google.com/search-console

GSC is the primary channel for monitoring Google's view of the site: indexing status, structured data errors, Core Web Vitals, and search performance. Set it up before submitting a sitemap so the submission has a destination.

**Verification**

Preferred method for a static Astro site: DNS TXT record (no code change needed) or HTML file dropped in `public/` (deploys to `dist/` at build time, served at the root).

- DNS TXT: add a `google-site-verification=...` TXT record to the `dangerousrobot.org` DNS zone. Requires DNS provider access. Persists through redeploys.
- HTML file: create `public/google<token>.html` with the content GSC provides. Simpler but ties verification to the deployed file.

DNS TXT is preferred because it survives `public/` directory changes.

**After verification:**

1. Set the canonical domain. GSC treats `dangerousrobot.org` and `www.dangerousrobot.org` as separate properties unless a domain property is used. Use a **Domain property** (not URL-prefix property) at setup — it covers all subdomains and both HTTP/HTTPS automatically.
2. Submit the sitemap (see dependency note below).
3. After public launch, use the URL Inspection tool to request indexing of key pages: `/`, `/claims`, `/companies`, `/criteria`, `/faq`.

**Dependency:** Sitemap submission requires `@astrojs/sitemap` to be implemented and deployed. Do not submit a sitemap until `sitemap.xml` exists at `https://dangerousrobot.org/sitemap-index.xml` and lists expected URLs.

### 2. Bing Webmaster Tools

**URL:** https://www.bing.com/webmasters

Bing Webmaster Tools covers Bing search (and, by extension, DuckDuckGo and other Bing-powered engines). Lower traffic volume than Google but costs little to set up.

**Setup order:** Do GSC first. Bing Webmaster can import your site and sitemap directly from GSC via its "Import from Google Search Console" flow, which avoids re-doing verification.

**After import:** Confirm the sitemap was imported correctly and request indexing of key pages via the URL Submission tool.

---

## Milestone: Google Fact Check program

**Status:** `[ ] gated — prereqs not met`

**Gating conditions (all must be true before applying):**

1. Alpha banner is removed from the site (pre-launch banner signals the site is not ready for editorial review).
2. A minimum set of published claims exists. Google does not publish a hard threshold for Fact Check program inclusion. The IFCN application process (the path Google uses) reviews editorial standards and methodology rather than claim count. In practice, apply only after the site has a meaningful corpus of published, sourced claims that demonstrates consistent methodology — not a handful. Operator judgment on readiness; revisit this gate when v1 content is published.
3. `ClaimReview` JSON-LD schema is implemented on claim pages (code plan dependency).
4. The site is indexed by Google (confirm via GSC URL Inspection).

### What the program is

Google surfaces approved fact-checkers in a dedicated "Fact Check" carousel in search results and in the Fact Check Explorer tool. For a research site like dangerousrobot.org — which evaluates specific claims made by AI companies — this is the highest-value external SEO opportunity available. Approved sites get their ClaimReview markup surfaced directly in Google results for the claims they've evaluated.

### How to apply

The path to Google's Fact Check program runs through the Duke Reporters' Lab, which maintains the International Fact-Checking Network (IFCN) database. Google uses IFCN certification as a primary signal.

1. **Review IFCN principles:** https://ifcncodeofprinciples.poynter.org — the code of principles covers non-partisanship, standards, funding transparency, and corrections policy. dangerousrobot.org's published methodology and conflict-of-interest disclosures in the FAQ are a start; review whether they meet IFCN's transparency requirements.
2. **Apply to the Duke Reporters' Lab fact-checker index:** https://reporterslab.org/fact-checking/ — this is the submission point for new fact-checkers. The Lab reviews and adds verified fact-checkers to a public database that Google queries.
3. **Google Fact Check Tools:** https://toolbox.google.com/factcheck/explorer — use this to search for your own domain after indexing to verify Google has picked up your `ClaimReview` markup. If claims appear here, the structured data is working.
4. **Approval timeline:** Weeks to months. Submit only after all gating conditions above are met. A premature or rejected application can delay acceptance.

### Notes

- The IFCN application asks for evidence of methodological transparency, corrections policies, funding sources, and editorial independence. Prepare a short document covering each before applying.
- dangerousrobot.org's conflict-of-interest disclosure (operator also runs TreadLightly AI) should be addressed directly in the application. The FAQ already carries the canonical disclosure; reference it.
- Google also surfaces fact-checks without IFCN certification if `ClaimReview` schema is implemented and the site has domain authority. IFCN certification accelerates and solidifies placement but is not the only path.

---

## Milestone: Validation and testing

**Status:** `[ ] gated — code plan must land first`

**Gating condition:** The code-side SEO changes (ClaimReview schema, FAQPage schema, BreadcrumbList schema, OG tags, twitter:card tags, sitemap, font loading changes) must be deployed to production before running these tools.

Run each tool below once after the first SEO-complete deploy, then re-run any that returned errors after fixes land.

### 1. Google Rich Results Test

**URL:** https://search.google.com/test/rich-results

Tests: `ClaimReview`, `FAQPage`, `BreadcrumbList` JSON-LD markup.

What to test:
- A claim page URL (e.g., `https://dangerousrobot.org/claims/some-claim`) for `ClaimReview`
- `/faq` for `FAQPage`
- Any page with breadcrumbs for `BreadcrumbList`

Passing result: the tool reports "Valid items detected" for each schema type tested, with no errors and no warnings. A green result for `ClaimReview` is a prerequisite for Google Fact Check program placement.

If it fails: check the JSON-LD for syntax errors, missing required fields (`claimReviewed`, `reviewRating`, `itemReviewed`), or field type mismatches. The tool surfaces the specific field that failed.

### 2. Schema.org Validator

**URL:** https://validator.schema.org

Tests: JSON-LD structure against the full Schema.org specification (broader than Google's subset).

What to test: paste the JSON-LD from a claim page. The validator shows all detected types and flags any property violations.

Passing result: no errors. Warnings about optional properties are acceptable.

If it fails: typically a missing required property or a type mismatch. Cross-reference the `ClaimReview` spec at https://schema.org/ClaimReview.

### 3. OpenGraph tag verification

**URL:** https://www.opengraph.xyz or https://metatags.io

Tests: `og:title`, `og:description`, `og:image`, `og:url` rendering.

What to test: the homepage, a claim page, and a company page.

Passing result: all four OG tags populate correctly; preview image renders and is not cropped unexpectedly; title and description are not truncated. If `og:image` is missing, social shares will render without an image.

If it fails: verify the `<meta property="og:...">` tags are present in the rendered HTML (view-source or DevTools), and that `og:image` points to an absolute URL (not a relative path).

### 4. Twitter Card Validator

**URL:** The dedicated Twitter Card Validator (`cards-dev.twitter.com/validator`) was retired by X/Twitter circa 2023.

Alternatives:
- **metatags.io** (https://metatags.io) and **opengraph.xyz** (https://www.opengraph.xyz) both render `twitter:card` previews alongside OG tags and are the practical replacements.
- **X Post Inspector** (https://cards-dev.twitter.com/validator) may still exist for logged-in users at time of testing — check, but don't depend on it.

Tests: `twitter:card`, `twitter:title`, `twitter:description`, `twitter:image` tags.

What to test: homepage and a claim page using metatags.io or opengraph.xyz.

Passing result: card preview renders correctly with the expected type (`summary_large_image` or `summary`), title, description, and image.

If it fails: confirm `twitter:card` is set and that `twitter:image` is an absolute URL. Twitter/X caches card metadata; after a fix, use a fresh URL in the preview tool or append a query string to bust the cache.

### 5. Google PageSpeed Insights

**URL:** https://pagespeed.web.dev

Tests: Core Web Vitals — Largest Contentful Paint (LCP), Cumulative Layout Shift (CLS), Interaction to Next Paint (INP) — plus overall performance score.

What to test: homepage and a claim page. Run both mobile and desktop.

Passing result: LCP under 2.5s, CLS under 0.1, INP under 200ms. A performance score of 90+ is a reasonable target for a static Astro site.

If it fails: the most common causes on a static site are unoptimized images (use `<Image />` from `@astrojs/image`), render-blocking fonts (use `font-display: swap` or preload), and large JS bundles. Font loading changes from the code plan should reduce LCP.

### 6. Sitemap validator

**URL:** https://www.xml-sitemaps.com/validate-xml-sitemap.html (or any sitemap linting tool)

Tests: that `sitemap.xml` (or `sitemap-index.xml`) is well-formed XML and lists the expected URLs.

What to test: `https://dangerousrobot.org/sitemap-index.xml`

Passing result: no XML parse errors; all key pages (`/`, `/claims/*`, `/companies/*`, `/criteria/*`) appear in the sitemap; `<lastmod>` dates are present and plausible.

If it fails: common causes are malformed XML (usually an unescaped `&` in a URL), missing pages (check `@astrojs/sitemap` include/exclude config), or a `robots.txt` that blocks the sitemap path.

---

## Milestone: Link building and citation outreach

**Status:** `[ ] ongoing — start at launch`

For a research site, domain authority grows through citations from credible external sources. This milestone is long-term and does not have a hard end date.

### 1. TreadLightly AI cross-linking

TreadLightly AI (treadlightly.ai) is the primary sponsor and a natural citation partner. Any claim made on the TreadLightly site that is backed by dangerousrobot.org research should link to the specific claim page, not just the homepage.

Most link-worthy pages at launch:
- Individual claim pages with published verdicts (deepest, most citable)
- Company entity pages (e.g., `/companies/microsoft`) as a source hub for all claims about that company
- `/criteria` pages explaining the evaluation framework

Action: audit which TreadLightly AI pages make assertions about AI company environmental claims and add or update source links to point at dangerousrobot.org claim pages rather than primary sources directly.

### 2. GitHub README

The README at `github.com/dangerous-robot/site` already links to the live site: `[dangerousrobot.org](https://dangerousrobot.org)`. This is confirmed present. No change needed for the homepage link. Consider whether to also add links from the README to specific published claims as examples.

### 3. Research citation tracking

Once the site is indexed, track inbound links via GSC's "Links" report (Search Console → Links → External links). When a journalist, organization, or researcher cites a dangerousrobot.org page:

- Record the citation in a simple log (a `research/citations.md` file is sufficient).
- Note which page was cited and the citing domain — this informs which content to prioritize for updates and which topic areas have external interest.

No outreach needed for organic citations. For planned outreach (pitching research to journalists), defer until the site has substantial published content post-v1.

### 4. Fact-check aggregator submission

After the Google Fact Check program application is approved (see that milestone), submit to other fact-check aggregators and indexes:

- **Duke Reporters' Lab database** (submission is part of the IFCN/Google path — already covered above)
- **ClaimBuster** (https://idir.uta.edu/claimbuster/) — an automated claim detection tool that partners with fact-checkers; worth monitoring once the site has volume
- **GDELT Fact Check data** — GDELT ingests ClaimReview markup automatically once the site is indexed and producing structured data; no manual submission needed

---

## Milestone: Monitoring and maintenance

**Status:** `[ ] ongoing — start after indexing`

**Gating condition:** GSC is verified and the site is indexed (at minimum the homepage returns a "URL is on Google" result in GSC URL Inspection).

### Monitoring cadence

| Signal | Tool | Frequency | Action threshold |
|--------|------|-----------|-----------------|
| Search performance (queries, clicks, impressions, CTR) | GSC → Performance | Monthly | Investigate pages with declining impressions over 2 consecutive months |
| Core Web Vitals | GSC → Core Web Vitals | Monthly | Any URL entering "Poor" status → fix within 2 weeks |
| Index coverage | GSC → Pages | Monthly | Unexpected "Not indexed" or "Excluded" URLs → investigate within 2 weeks |
| Structured data errors | GSC → Enhancements | Monthly | Any `ClaimReview` or `FAQPage` errors → fix within 1 week (blocks Fact Check placement) |
| Inbound links | GSC → Links | Quarterly | Log notable citations; update `research/citations.md` |

### What to watch for

**Index coverage:** Pages marked "Discovered — currently not indexed" or "Crawled — currently not indexed" may indicate thin content or a crawl budget issue. A static site with < 1,000 pages should not have crawl budget problems; focus on content quality if pages are excluded.

**ClaimReview errors:** GSC surfaces structured data errors in the Enhancements tab. A `ClaimReview` error on a claim page removes that claim from Fact Check program placement. Check this tab monthly; errors here are higher priority than performance regressions.

**Core Web Vitals regressions:** LCP and CLS can regress after Astro upgrades, image changes, or new layout components. The GSC "Core Web Vitals" report uses real-user data (CrUX), which lags 28 days. If PageSpeed Insights (lab data) shows a regression, investigate immediately rather than waiting for CrUX to confirm.

**Search query data:** GSC Performance shows what queries drive impressions and clicks. For dangerousrobot.org, useful signals include:
- Which company names drive queries (indicates which entity pages are getting traction)
- Whether informational queries ("does Microsoft buy carbon offsets") are landing on claim pages
- CTR below 2% on pages with > 100 impressions suggests the title or meta description should be revised

---

## Dependencies

| This milestone | Depends on |
|----------------|-----------|
| Search console setup → sitemap submission | `@astrojs/sitemap` implemented and deployed |
| Google Fact Check program | Alpha banner removed; meaningful corpus of published claims; ClaimReview schema deployed; site indexed |
| Validation and testing | All code-side SEO changes deployed to production |
| Monitoring and maintenance | GSC verified; site indexed |

## Cross-references

- Code-side SEO plan (sitemap, JSON-LD, meta tags, font loading) — see the technical SEO plan (not yet filed)
- Alpha banner removal — tracked in [`pre-launch-quick-fixes.md`](pre-launch-quick-fixes.md) (S1, currently live; removal is post-launch)
- ClaimReview schema — required by the Google Fact Check milestone; tracked in technical SEO plan

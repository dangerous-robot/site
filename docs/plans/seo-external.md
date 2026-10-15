# Plan: external SEO: dangerousrobot.org

| Milestone | Status |
|-----------|--------|
| Search console setup | `[~] partly done`: GSC verified, sitemap submitted, inspection baseline from 2026-05-11. Open now: inspection re-run, Request Indexing pass, Bing (unverified: check Bing) |
| Validation and testing | `[ ] do now`: no gate; no results recorded in `seo-runs/` |
| Monitoring and maintenance | `[ ] do now` for site-level rows (the homepage was indexed at the 2026-05-11 baseline); claim-level rows wait for the indexing flip |
| Link building and citation outreach | `[ ] not now`: waits for the indexing flip and launch |
| Google Fact Check program | `[ ] not now`: gated; prerequisites not met, including the indexing flip and ClaimReview markup |

**What can be done now.** Every page except claim, source and entity detail pages is indexable today: the homepage, `/resources` and its five guides, the `/research` hub and list pages, `/research/criteria/*`, `/research/topics/*`, `/writing` and its post, `/petitions/prohibit-ai-self-improvement`, `/about`, `/values`, `/corrections`, `/credits`, `/privacy`, `/people/brandon-f`. These can be validated, inspected, submitted and monitored now. `/resources/responsible-ai` matters most: it is the page SITE-J (Responsible AI chatbots, backed by claims) is building, the top priority in `docs/priorities.md`, and it is indexable before the flip.

**Indexing gate.** Claim, source and entity pages stay `noindex` and out of the sitemap until after 1.0.0; Brandon decides the trigger (`docs/decisions.md:19`). The switch is `INDEX_ALPHA_DETAIL_PAGES` in `src/lib/seo.ts`. Only the milestones that need those pages in Google's index wait for the flip. The first reader is a concerned person at a decision point, not a fact-checking audience (`docs/mission-and-voice.md`), so the Fact Check program and journalist outreach rank below getting the guide pages found.

**Known gap.** Subject claim pages (`/research/claims/subjects/{subject}/{claim}`) are indexable and listed in the sitemap today, against the decision above. The claim pattern in `src/lib/seo.ts:35` matches two path segments after `/research/claims/`; subject claims have three. Checked live 2026-10-09: `/research/claims/subjects/ai-model-producers/ai-producers-existential-score` serves `index,follow` and appears in `sitemap-0.xml`. The fix is SITE-Y (Subject claim noindex) in the roadmap. Until it lands, leave subject claim pages out of every Request Indexing list.

**Known gap, URL form.** Every page except `/` 301s to its trailing-slash form (`/about` → `/about/`) while the canonical tag and the sitemap use the no-slash form (`trailingSlash: "never"` in `astro.config.ts`, GitHub Pages serving `about/index.html`). Checked live 2026-10-09. Google tolerates it, but every sitemap URL is a redirect. Decided 2026-10-09 (`docs/decisions.md` "URLs end in a slash"); the fix is SITE-Z (Trailing-slash URLs) in the roadmap. Run N4 after it lands.

---

## Do now

Each item needs no code change and no gate. `seo-runs/` is git-ignored (local only); save evidence there by date.

| # | Action | Tool or script | Pages | Expected result | Save to |
|---|--------|----------------|-------|-----------------|---------|
| N1 | Re-run the URL inspection against the 2026-05-11 baseline | `scripts/seo/inspect-urls.sh` (needs `GSC_QUOTA_PROJECT` exported and gcloud application-default login) | The 18 URLs in the script: homepage, `/resources` and four guides, `/research` hub and list pages, `/values`, `/credits`, plus old `/claims` and `/companies` | `/resources/*` and `/research/*` have left "URL is unknown to Google"; old `/claims` and `/companies` show "Page with redirect" with a `/research/...` canonical, or have left the index. Note any sitemap URL reported as "Page with redirect" (every page 301s to its trailing-slash form) | `seo-runs/urlinspect-YYYY-MM-DD/` (the script writes it) |
| N2 | Inspect the pages the script does not cover | GSC → URL Inspection | `/resources/ai-safety-winter-2025`, `/writing`, `/writing/why-dangerous-robot-exists`, `/petitions/prohibit-ai-self-improvement`, `/about`, `/corrections`, `/privacy`, `/people/brandon-f`, and the two subject claim pages (expected indexed today; see Known gap) | Each is "URL is on Google" or "Discovered"; none is blocked by `noindex` or robots.txt | One line per URL in `seo-runs/urlinspect-YYYY-MM-DD/manual.md` |
| N3 | Capture index coverage once | GSC → Pages | Whole property | Counts for Indexed, Page with redirect, Crawled - not indexed, Discovered - not indexed | `seo-runs/coverage-YYYY-MM-DD.json` |
| N4 | Request Indexing for pages N1 or N2 found not indexed | GSC → URL Inspection → Request Indexing | `/resources/responsible-ai` first, then the order in the playbook ("Force initial indexing of key pages") | Request accepted; page moves to indexed on a later inspection | Append the date and URLs to the N2 note |
| N5 | Run the validation tools | See "Validation and testing" below | `/research`, `/resources/turn-off-ai`, `/about`, homepage, `/resources/responsible-ai`, the petition page | No errors in Rich Results or the Schema.org validator; share previews show title, description and image; PageSpeed scores recorded | Screenshots or a results note in `seo-runs/validation-YYYY-MM-DD/` |
| N6 | Set up Bing Webmaster Tools, if not already done (unverified: check Bing) | https://www.bing.com/webmasters → Import from Google Search Console | Whole property | Site and sitemap imported | One line in the N2 note |
| N7 | Start the monthly GSC check | Monitoring table below; playbook "Recurring checks" | Whole property | No manual actions, no 5xx, sitemap status Success | A dated line in the coverage file |

---

## Background

This plan covers external platform registrations, submissions, validations, and monitoring tasks. Nothing here requires code changes to the site. The code-side SEO work (sitemap, JSON-LD, meta tags, font loading) shipped in [`completed/seo-technical.md`](completed/seo-technical.md).

Domain: `dangerousrobot.org` (bare domain, no www). Confirmed via `public/CNAME`. The GitHub README links to the live site at `https://dangerousrobot.org`.

---

## Milestone: Search console setup

**Status:** `[~] partly done`. GSC is verified as a Domain property (`sc-domain:dangerousrobot.org`), the sitemap is submitted, and the inspection baseline is in `seo-runs/urlinspect-2026-05-11/`. Open: the inspection re-run (N1, N2), a Request Indexing pass (N4), and Bing (N6). No record exists of a Request Indexing pass or of Bing setup.

**Gating condition:** none. The site is publicly accessible.

### 1. Google Search Console (GSC)

**URL:** https://search.google.com/search-console

GSC is the primary channel for monitoring Google's view of the site: indexing status, structured data errors, Core Web Vitals, and search performance.

**Verification:** DNS TXT record in Cloudflare, on a Domain property (covers apex, www, HTTP and HTTPS). Done.

**Sitemap:** `https://dangerousrobot.org/sitemap-index.xml`, submitted. `scripts/seo/submit-sitemap.sh` resubmits it through the API.

**Request Indexing:** use the URL Inspection tool on key indexable pages, in the order the playbook lists ("Force initial indexing of key pages"), `/resources` guides first. `scripts/seo/request-indexing-queue.txt` holds the first 10. Claim, source and entity pages wait for the indexing flip.

### 2. Bing Webmaster Tools

**URL:** https://www.bing.com/webmasters

Bing Webmaster Tools covers Bing search (and, by extension, DuckDuckGo and other Bing-powered engines). Lower traffic volume than Google but costs little to set up.

**Setup:** use "Import from Google Search Console", which avoids re-doing verification. Then confirm the sitemap was imported and submit key pages through the URL Submission tool. Unverified whether this was ever done: check Bing first.

---

## Milestone: Validation and testing

**Status:** `[ ] do now` (no gate; the code-side SEO changes are deployed). No results are recorded in `seo-runs/`.

Run each tool below once, save the result (N5), then re-run any that returned errors after fixes land. Claim pages emit no `ClaimReview` markup, so it is not tested.

What the site emits today (`src/layouts/Base.astro`): canonical, `robots`, OG and Twitter tags on every page, and `Organization` JSON-LD on every page. The homepage adds `WebSite` with a `SearchAction`; `/research` and `/resources/turn-off-ai` add `FAQPage`; pages with a breadcrumb (for example `/about`, `/writing`, writing posts) add `BreadcrumbList`. The default `og:image` is `/dr-logo-light-bg.png` (512×512, square) with `twitter:card` set to `summary_large_image`. A writing post or petition with an `image` field gets a 1200px JPEG share image instead (`src/lib/share-image.ts`); today only the petition page has one.

### 1. Google Rich Results Test

**URL:** https://search.google.com/test/rich-results

What to test:
- `/research` and `/resources/turn-off-ai` for `FAQPage`
- `/about` for `BreadcrumbList`

Passing result: "Valid items detected" for each schema type tested, with no errors.

If it fails: check the JSON-LD for syntax errors, missing required fields, or field type mismatches. The tool surfaces the specific field that failed.

### 2. Schema.org Validator

**URL:** https://validator.schema.org

Tests: JSON-LD structure against the full Schema.org specification (broader than Google's subset).

What to test: the homepage (`Organization`, `WebSite`) and `/about` (`BreadcrumbList`).

Passing result: no errors. Warnings about optional properties are acceptable.

If it fails: typically a missing required property or a type mismatch. Cross-reference the type's spec on https://schema.org.

### 3. OpenGraph and Twitter card previews

**URL:** https://www.opengraph.xyz or https://metatags.io (both render OG and `twitter:card` previews; the old Twitter Card Validator is retired)

Tests: `og:title`, `og:description`, `og:image`, `og:url`, and the `twitter:*` tags.

What to test: the homepage, `/resources/responsible-ai`, and `/petitions/prohibit-ai-self-improvement` (the page with its own share image).

Passing result: tags populate; title and description are not truncated; the petition page shows its own image. Expect the square logo on the other two, which large-card previews may crop: record how it looks.

If it fails: check that the tags are in the rendered HTML (view-source) and that `og:image` is an absolute URL. Preview tools cache; append a query string to bust the cache after a fix.

### 4. Google PageSpeed Insights

**URL:** https://pagespeed.web.dev

Tests: Core Web Vitals (Largest Contentful Paint, Cumulative Layout Shift, Interaction to Next Paint) plus overall performance score.

What to test: the homepage and `/resources/responsible-ai`. Run both mobile and desktop.

Passing result: LCP under 2.5s, CLS under 0.1, INP under 200ms. A performance score of 90+ is a reasonable target for a static Astro site.

If it fails: the most common causes on a static site are unoptimized images, render-blocking fonts, and large JS bundles.

### 5. Sitemap check

**URL:** https://www.xml-sitemaps.com/validate-xml-sitemap.html (or any sitemap linting tool)

What to test: `https://dangerousrobot.org/sitemap-index.xml`

Passing result: no XML parse errors; the indexable pages listed under "What can be done now" appear; no claim, source or entity detail pages appear (subject claim pages do today: see "Known gap").

If it fails: common causes are malformed XML, the sitemap `filter` in `astro.config.ts`, or a `robots.txt` that blocks the sitemap path.

---

## Milestone: Monitoring and maintenance

**Status:** `[ ] do now` for site-level rows. The homepage was "Submitted and indexed" in the 2026-05-11 baseline. Claim-level rows (search queries landing on claim pages, claim page coverage) wait for the indexing flip.

This table is the one source for the monitoring cadence; the playbook's "Recurring checks" section points here.

### Monitoring cadence

| Signal | Tool | Frequency | Action threshold |
|--------|------|-----------|-----------------|
| Index coverage | GSC → Pages | Monthly | Unexpected "Not indexed" or "Excluded" URLs → investigate within 2 weeks |
| Sitemap status | GSC → Sitemaps | Monthly | Status not "Success" → investigate |
| Manual actions and security issues | GSC → Security & Manual actions | Monthly | Anything listed → investigate immediately |
| Structured data errors | GSC → Enhancements | Monthly | Any `FAQPage` or `BreadcrumbList` errors → fix within 1 week |
| Core Web Vitals | GSC → Core Web Vitals | Monthly | Any URL entering "Poor" status → fix within 2 weeks |
| Search performance (queries, clicks, impressions, CTR) | GSC → Performance | Monthly | Investigate pages with declining impressions over 2 consecutive months |
| Inbound links | GSC → Links | Quarterly | Log notable citations; update `research/citations.md` |

### What to watch for

**Index coverage:** "Discovered - currently not indexed" usually needs time and external links. "Crawled - currently not indexed" may indicate thin or duplicate content. A static site with < 1,000 pages should not have crawl budget problems; focus on content quality if pages are excluded. "Server error (5xx)" or "Redirect error": investigate immediately.

**Core Web Vitals regressions:** LCP and CLS can regress after Astro upgrades, image changes, or new layout components. The GSC report uses real-user data, which lags. If PageSpeed Insights (lab data) shows a regression, investigate rather than waiting for the GSC report.

**Search query data:** GSC Performance shows what queries drive impressions and clicks. Useful signals:
- Which `/resources` guides get impressions, and for which queries
- After the flip: whether informational queries land on claim pages
- CTR below 2% on pages with > 100 impressions suggests the title or meta description should be revised

---

## Milestone: Link building and citation outreach

**Status:** `[ ] not now`. Waits for the indexing flip (after 1.0.0) and launch; the most link-worthy pages are claim pages, which are `noindex` until then.

For a research site, domain authority grows through citations from credible external sources. This milestone is long-term and does not have a hard end date.

### 1. TreadLightly AI cross-linking

TreadLightly AI (treadlightly.ai) is made by the same person who runs Dangerous Robot (see `/about`); it is not a sponsor, and links from it carry that conflict of interest. Any claim made on the TreadLightly site that is backed by dangerousrobot.org research should link to the specific claim page, not just the homepage.

Most link-worthy pages after the flip:
- Individual claim pages with published verdicts (deepest, most citable)
- Entity pages (for example `/research/entities/products/chatgpt`) as a source hub for all claims about that product or subject
- `/research/criteria` pages explaining the evaluation framework

Action: audit which TreadLightly AI pages make assertions about AI company environmental claims and add or update source links to point at dangerousrobot.org claim pages rather than primary sources directly.

### 2. GitHub README

The README at `github.com/dangerous-robot/site` links to the live site. Consider whether to also add links to specific published claims as examples.

### 3. Research citation tracking

Track inbound links via GSC's "Links" report (Search Console → Links → External links). When a journalist, organization, or researcher cites a dangerousrobot.org page:

- Record the citation in a simple log (a `research/citations.md` file is sufficient).
- Note which page was cited and the citing domain.

No outreach needed for organic citations. Planned outreach to journalists waits until the site has substantial published content after 1.0.0.

### 4. Fact-check aggregator submission

Only after the Google Fact Check program application is approved (see that milestone):

- **Duke Reporters' Lab database** (part of the IFCN/Google path, covered in that milestone)
- **ClaimBuster** (https://idir.uta.edu/claimbuster/): an automated claim detection tool that partners with fact-checkers; worth monitoring once the site has volume
- **GDELT Fact Check data**: ingests ClaimReview markup, which claim pages do not emit; applies only if the markup is added back

---

## Milestone: Google Fact Check program

**Status:** `[ ] not now`. Gated on all four conditions below; none is met today.

Claim pages emit no `ClaimReview` markup: it was removed on 2026-10-07 (`docs/decisions.md`) because Google removed ClaimReview rich results from Search in 2025 and Fact Check Explorer listing is limited to approved fact-check publishers. Verdicts and ratings stay in the claim files, so it can be added back if this milestone is pursued.

**Gating conditions (all must be true before applying):**

1. The pre-release banner is removed from the site. It shows while the version has an alpha, beta or rc label (`src/layouts/Base.astro`).
2. A meaningful corpus of published, sourced claims exists that demonstrates consistent methodology. Google publishes no hard threshold; the IFCN application reviews editorial standards and methodology rather than claim count. Operator judgment on readiness.
3. `ClaimReview` JSON-LD is added back to claim pages (code change).
4. Claim pages are indexed by Google, which needs the indexing flip first (confirm via GSC URL Inspection).

### What the program is

Google surfaces approved fact-checkers in Fact Check Explorer. For a site that evaluates specific claims made by AI companies, it is a possible channel, ranked below getting the guide pages found (see "Indexing gate").

### How to apply

The path to Google's Fact Check program runs through the Duke Reporters' Lab, which maintains a fact-checker database, and the International Fact-Checking Network (IFCN). Google uses IFCN certification as a primary signal.

1. **Review IFCN principles:** https://ifcncodeofprinciples.poynter.org. The code covers non-partisanship, standards, funding transparency, and corrections policy. dangerousrobot.org's published methodology and conflict-of-interest disclosures are a start; review whether they meet IFCN's transparency requirements.
2. **Apply to the Duke Reporters' Lab fact-checker index:** https://reporterslab.org/fact-checking/.
3. **Google Fact Check Tools:** https://toolbox.google.com/factcheck/explorer. After indexing, search for the domain to check whether Google has picked up the `ClaimReview` markup.
4. **Approval timeline:** weeks to months. Submit only after all gating conditions are met. A premature or rejected application can delay acceptance.

### Notes

- The IFCN application asks for evidence of methodological transparency, corrections policies, funding sources, and editorial independence. Prepare a short document covering each before applying.
- The conflict-of-interest disclosure (the operator also runs TreadLightly AI) should be addressed directly in the application. `/about` and the `/research` FAQ carry the disclosure; reference them.

---

## Dependencies

| This milestone | Depends on |
|----------------|-----------|
| Search console setup | Nothing open (sitemap deployed and submitted) |
| Validation and testing | Code-side SEO changes deployed (done) |
| Monitoring and maintenance | GSC verified (done); homepage was indexed at the 2026-05-11 baseline; claim-level rows need the indexing flip |
| Link building and citation outreach | Indexing flip (after 1.0.0); launch |
| Google Fact Check program | Pre-release banner removed; meaningful corpus of published claims; ClaimReview markup added back; indexing flip; claim pages indexed |

## Cross-references

- Operator checklist (GSC steps, Cloudflare settings, the flip procedure): [`../seo-and-cloudflare-playbook.md`](../seo-and-cloudflare-playbook.md)
- Code-side SEO plan (sitemap, JSON-LD, meta tags, font loading): [`completed/seo-technical.md`](completed/seo-technical.md)
- URL restructure, Cloudflare redirects and the 2026-05-11 baseline: [`completed/seo-post-restructure.md`](completed/seo-post-restructure.md)
- Pre-release banner: added in [`completed/pre-launch-quick-fixes.md`](completed/pre-launch-quick-fixes.md) (S1); removal is post-launch
- ClaimReview markup: removed from claim pages ([`completed/site-j-claims-readiness.md`](completed/site-j-claims-readiness.md) CR5, `docs/decisions.md` 2026-10-07)
- Indexing flip: `src/lib/seo.ts`; procedure in the playbook ("When the pre-release noindex period ends")

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-07-03 | agent (claude-fable-5) | basic | Section added during docs audit; search-console milestone updated to reflect the 2026-05-11 GSC/baseline work; one link repointed to completed/. |
| 2026-10-06 | agent (claude-opus-5-5, plan review) | refocus alignment | Added the indexing gate (first guide, roadmap §9 J); validation gate marked met; TreadLightly described as made by the same person, not a sponsor; URLs moved to `/research/...`; cross-references point at shipped work. |
| 2026-10-07 | agent (claude-opus-5-5) | basic, iterated | ClaimReview removed from claim pages (`site-j-claims-readiness.md` CR5): dropped from the validation gate, test lists and monitoring; the Fact Check program gate now needs it added back. |
| 2026-10-09 | agent (claude-opus-5-5) | immediate priorities | Added "Do now" (N1 to N7) and reordered milestones so ungated work comes first; indexing gate now says after 1.0.0, Brandon's call; recorded the subject-claim indexing gap (`seo.ts:35`, checked live); validation targets fixed (`/faq` redirects, FAQPage on `/research` and `/resources/turn-off-ai`, default `og:image` is the square `dr-logo-light-bg.png`); monitoring table is the single cadence source. |

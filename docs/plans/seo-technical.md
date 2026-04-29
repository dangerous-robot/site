# Plan: SEO — technical and code improvements

| Milestone | Status |
|-----------|--------|
| Crawlability | `[ ] ready to implement` |
| Meta tags | `[ ] ready to implement` |
| Structured data | `[ ] ready to implement` |
| Performance | `[ ] ready to implement` |

---

## Background

This plan covers the technical/code SEO improvements identified in an SEO audit of dangerousrobot.org. It does not cover content SEO (title copy, heading hierarchy, internal linking strategy), which belongs in a separate plan.

The site is Astro 6.x, statically generated, deployed to `dangerousrobot.org`. Content is driven by Astro content collections (`claims`, `entities`, `sources`, `criteria`). The improvements are grouped into four milestones that can be implemented sequentially in order.

---

## Milestone: Crawlability

**Status:** `[ ] ready to implement`

### 1. robots.txt

Create `/public/robots.txt`. Astro copies everything in `public/` to `dist/` verbatim, so this file lands at `https://dangerousrobot.org/robots.txt` with no additional config.

**File to create: `public/robots.txt`**

```
User-agent: *
Allow: /

Sitemap: https://dangerousrobot.org/sitemap-index.xml
```

There are no non-public paths that need to be disallowed. All pages are publicly intentional. The `Sitemap:` URL references the index file that `@astrojs/sitemap` generates (see item 2).

If a path like `/admin/` or a staging-only route is added in the future, add a `Disallow:` line at that time.

### 2. Sitemap

Install `@astrojs/sitemap` and configure it in `astro.config.ts`.

```bash
npm install @astrojs/sitemap
```

**Updated `astro.config.ts`:**

```ts
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://dangerousrobot.org",
  trailingSlash: "never",
  integrations: [
    sitemap({
      changefreq: "weekly",
      priority: 0.7,
      lastmod: new Date(),
      customPages: [],
      filter: (page) => !page.includes("/404"),
    }),
  ],
});
```

`@astrojs/sitemap` discovers all static routes automatically. Dynamic routes (`/claims/[...slug]`, `/entities/[...slug]`, etc.) are included because `getStaticPaths()` is called at build time and the integration inspects the generated pages in `dist/`.

**`changefreq` and `priority` decisions:**

The integration supports a per-page override via the `serialize` callback, which receives the page URL. Use it to differentiate claim pages from index pages:

```ts
sitemap({
  changefreq: "weekly",
  priority: 0.7,
  serialize(item) {
    // Claim pages: highest priority — this is the core content
    if (item.url.includes("/claims/")) {
      return { ...item, changefreq: "monthly", priority: 0.9 };
    }
    // Entity pages: high priority — aggregation pages for a company/product
    if (item.url.includes("/entities/") || item.url.includes("/companies/") || item.url.includes("/products/")) {
      return { ...item, changefreq: "weekly", priority: 0.8 };
    }
    // Sources index: crawlers should see new sources, but it's secondary
    if (item.url === "https://dangerousrobot.org/sources") {
      return { ...item, changefreq: "weekly", priority: 0.5 };
    }
    // Source detail pages: low priority — supporting content, not primary
    if (item.url.includes("/sources/")) {
      return { ...item, changefreq: "monthly", priority: 0.4 };
    }
    // Topics, Criteria, FAQ, etc.
    return { ...item, changefreq: "weekly", priority: 0.7 };
  },
}),
```

**Rationale:** Claim pages are the canonical research output. They should be indexed and recrawled first. Source detail pages are reference material; search engines should find them via claim pages, not as entry points.

### 3. Trailing slash

Add `trailingSlash: "never"` to `astro.config.ts` (already shown in item 2 above).

**Risk assessment:** Astro's `trailingSlash: "never"` setting changes two things: (a) the dev server redirects `/foo/` → `/foo`, and (b) the build generates `foo.html` instead of `foo/index.html` for each route.

The existing nav links in `Base.astro` and throughout the site use paths like `/claims`, `/entities/...`, `/topics`, etc., without trailing slashes. These are unaffected. The `CNAME` setup and GitHub Pages/Cloudflare Pages deployments handle extensionless URLs transparently.

**Verify before merging:** Run `npm run build` and confirm all internal links in the generated HTML resolve correctly. Also confirm no redirect loops when navigating from `/foo/` to `/foo` in the deployed environment.

If the host requires a different behavior (e.g., always-trailing), use `trailingSlash: "always"` instead. The key is consistency, not the specific choice. `"never"` is the cleaner option for a static site because it avoids the duplicate-content risk of `/foo` and `/foo/` both being accessible.

### Files changed (Crawlability)

| File | Change |
|------|--------|
| `public/robots.txt` | new: allow all, reference sitemap |
| `astro.config.ts` | add `@astrojs/sitemap` integration, add `trailingSlash: "never"` |
| `package.json` | add `@astrojs/sitemap` dependency |

---

## Milestone: Meta tags

**Status:** `[ ] ready to implement`

### 4. Canonical URL

Add `<link rel="canonical">` to `Base.astro`. `Astro.url.href` is the fully-qualified URL of the current page (e.g., `https://dangerousrobot.org/claims/microsoft/energy-sourcing`). It respects the `site` config in `astro.config.ts`.

In `Base.astro`, inside `<head>`, after the existing `<meta name="description">`:

```astro
<link rel="canonical" href={Astro.url.href} />
```

No prop needed: `Astro.url` is always available in layouts.

### 5. Open Graph tags

The `Props` interface in `Base.astro` needs an `ogImage?: string` field. The default falls back to `/dr-logo.png`, which already exists in `public/`. This is adequate for now; a proper 1200×630 social card image can replace it later without changing the schema.

**Updated `Props` interface in `Base.astro`:**

```ts
interface Props {
  title: string;
  description?: string;
  layout?: 'reading' | 'wide' | 'bare';
  chrome?: 'standard' | 'minimal';
  ogImage?: string;
}

const {
  title,
  description = "Structured research backing claims about AI products and companies.",
  layout = 'reading',
  chrome = 'standard',
  ogImage = '/dr-logo.png',
} = Astro.props;
```

**OG tags to add in `<head>` (after canonical):**

```astro
<!-- Open Graph -->
<meta property="og:type" content="website" />
<meta property="og:url" content={Astro.url.href} />
<meta property="og:title" content={`${title} - Dangerous Robot`} />
<meta property="og:description" content={description} />
<meta property="og:image" content={new URL(ogImage, Astro.site).href} />
```

`new URL(ogImage, Astro.site).href` converts the root-relative `/dr-logo.png` to a fully-qualified `https://dangerousrobot.org/dr-logo.png`. OG `image` must be an absolute URL.

For claim pages where the og:type should be `article`, callers can pass `ogImage` pointing to a future generated card image. The `og:type` is left as `website` globally; overriding it per page type would require a new prop, and `website` is not wrong for any of these page types.

### 6. Twitter/X card tags

Add after the OG block:

```astro
<!-- Twitter/X card -->
<meta name="twitter:card" content="summary" />
<meta name="twitter:title" content={`${title} - Dangerous Robot`} />
<meta name="twitter:description" content={description} />
<meta name="twitter:image" content={new URL(ogImage, Astro.site).href} />
```

`summary` (not `summary_large_image`) is the right default until a 1200×630 social card image exists. The logo at `/dr-logo.png` is square and looks correct in the `summary` card format.

When a social card image is added, update to `summary_large_image` and point `ogImage` default to the new image.

### 7. Dynamic descriptions

All dynamic page templates currently pass no `description` prop and fall back to the static default in `Base.astro`. The fix for each:

**`/src/pages/claims/[...slug].astro`**

`claim.data.takeaway` is the human-edited one-line summary. If present, it is the best description. Otherwise, prefix the claim title with the entity name to give context (the title alone can be ambiguous without knowing which company it's about).

Add before the `<Base>` call:

```astro
const claimDescription = claim.data.takeaway
  ?? `${entityLabel}: ${claim.data.title}`.slice(0, 155);
```

Update the `<Base>` call:

```astro
<Base title={claim.data.title} description={claimDescription}>
```

`entityLabel` is already computed on line 32 of the file: `const entityLabel = entityEntry?.data.name ?? claim.data.entity;`

**`/src/pages/entities/[...slug].astro`**

`entity.data.description` is already a required string field on entities. Use it directly:

```astro
<Base title={entity.data.name} description={entity.data.description}>
```

**`/src/pages/topics/[topic].astro`**

The template has `label` (the human-readable topic name) and `uniqueClaimCount` (the count of claims in this topic). Build the description from those:

```astro
const topicDescription = `${uniqueClaimCount} assessed claim${uniqueClaimCount !== 1 ? 's' : ''} on ${label} from AI companies and products.`;
```

Update the `<Base>` call:

```astro
<Base title={label} layout="wide" description={topicDescription}>
```

**`/src/pages/criteria/[slug].astro`**

The criterion has `std.data.text` (the criterion statement) and the `matchingEntities` array. Build from those:

```astro
const criteriaDescription = `${std.data.text} — assessed across ${matchingEntities.length} entit${matchingEntities.length !== 1 ? 'ies' : 'y'}.`;
```

Update the `<Base>` call:

```astro
<Base title={std.data.text} layout="wide" description={criteriaDescription}>
```

**`/src/pages/sources/[...slug].astro`**

The source has `source.data.publisher`, `source.data.kind`, and `source.data.title`. The `source.data.summary` field is also available and is already the best human-written description of the source. Use it:

```astro
const sourceDescription = source.data.summary
  ?? `${source.data.publisher} — ${source.data.kind}: ${source.data.title}`.slice(0, 155);
```

Update the `<Base>` call:

```astro
<Base title={source.data.title} description={sourceDescription}>
```

### Files changed (Meta tags)

| File | Change |
|------|--------|
| `src/layouts/Base.astro` | add `ogImage?` prop; add canonical, OG, and Twitter meta tags |
| `src/pages/claims/[...slug].astro` | compute `claimDescription`, pass to `<Base>` |
| `src/pages/entities/[...slug].astro` | pass `entity.data.description` to `<Base>` |
| `src/pages/topics/[topic].astro` | compute `topicDescription`, pass to `<Base>` |
| `src/pages/criteria/[slug].astro` | compute `criteriaDescription`, pass to `<Base>` |
| `src/pages/sources/[...slug].astro` | compute `sourceDescription`, pass to `<Base>` |

---

## Milestone: Structured data

**Status:** `[ ] ready to implement`

All structured data uses JSON-LD in `<script type="application/ld+json">` blocks. Inline in components and pages using Astro's `set:html` directive on a `<script>` tag, or as a raw `<script>` in the component's template section. The latter is simpler and avoids the `set:html` escaping concern for static data.

### 8. BreadcrumbList JSON-LD

`Breadcrumb.astro` already receives a `crumbs` array typed as `{ label: string; href?: string }[]`. The last crumb has no `href` (it's the current page). Reconstruct the absolute URL for the last crumb from `Astro.url.href`.

**Updated `Breadcrumb.astro`:**

```astro
---
interface Props { crumbs: { label: string; href?: string }[] }
const { crumbs } = Astro.props;

const siteOrigin = "https://dangerousrobot.org";

const breadcrumbList = {
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": crumbs.map((c, i) => ({
    "@type": "ListItem",
    "position": i + 1,
    "name": c.label,
    ...(c.href
      ? { "item": `${siteOrigin}${c.href}` }
      : { "item": Astro.url.href }),
  })),
};
---
<script type="application/ld+json" set:html={JSON.stringify(breadcrumbList)} />
<nav aria-label="Breadcrumb" class="breadcrumb">
  <!-- existing markup unchanged -->
</nav>
```

`Astro.url` is accessible in component scripts. `siteOrigin` is hardcoded rather than read from `Astro.site` to keep the component simpler; if the site domain changes, update here too (or import from a shared constant).

**Note:** The `set:html` directive on a `<script>` tag is how Astro handles injecting dynamic content into script blocks without escaping it as HTML entities. `JSON.stringify` produces valid JSON, so this is safe.

### 9. ClaimReview JSON-LD

Google's ClaimReview schema is the dedicated fact-check markup. Add it to `/src/pages/claims/[...slug].astro`.

**Verdict → ratingValue mapping:**

| Verdict | ratingValue | Label |
|---------|-------------|-------|
| `true` | 5 | True |
| `mostly-true` | 4 | Mostly true |
| `mixed` | 3 | Mixed |
| `mostly-false` | 2 | Mostly false |
| `false` | 1 | False |
| `unverified` | 3 | Unverified |
| `n-a` | 3 | Not applicable |

Rationale: The schema requires a 1–5 scale. `true` = 5, `false` = 1, graduated in between. `unverified` and `n-a` are both mapped to 3 (midpoint) because neither confirms nor refutes; 3 is the least misleading choice.

**Add to `[...slug].astro` frontmatter:**

```astro
const verdictRatingMap: Record<string, number> = {
  "true": 5,
  "mostly-true": 4,
  "mixed": 3,
  "mostly-false": 2,
  "false": 1,
  "unverified": 3,
  "n-a": 3,
};

const verdictLabelMap: Record<string, string> = {
  "true": "True",
  "mostly-true": "Mostly true",
  "mixed": "Mixed",
  "mostly-false": "Mostly false",
  "false": "False",
  "unverified": "Unverified",
  "n-a": "Not applicable",
};

const claimReview = {
  "@context": "https://schema.org",
  "@type": "ClaimReview",
  "url": Astro.url.href,
  "claimReviewed": claim.data.title,
  "datePublished": asOfDate,
  "author": {
    "@type": "Organization",
    "name": "Dangerous Robot",
    "url": "https://dangerousrobot.org",
  },
  "reviewRating": {
    "@type": "Rating",
    "ratingValue": verdictRatingMap[claim.data.verdict] ?? 3,
    "bestRating": 5,
    "worstRating": 1,
    "alternateName": verdictLabelMap[claim.data.verdict] ?? claim.data.verdict,
  },
};
```

**Add to the template (before `</article>`):**

```astro
<script type="application/ld+json" set:html={JSON.stringify(claimReview)} />
```

Only emit ClaimReview for published claims. Draft and archived claims should not be submitted to Google's fact-check index. Add a guard:

```astro
{!isDraft && !isArchived && (
  <script type="application/ld+json" set:html={JSON.stringify(claimReview)} />
)}
```

### 10. FAQPage JSON-LD

`/src/pages/faq/index.astro` uses `<details>`/`<summary>` elements. The question text is in `<summary>` and the answer is in `.answer`. Since the FAQ is static HTML (not data-driven), the JSON-LD can be hardcoded in the frontmatter.

Extract the Q&A pairs as a static array. Add to the frontmatter:

```astro
const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What is this site?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Dangerous Robot is a structured research project that routes human questions through a Python pipeline using LLM agents to find sources, fetch content, evaluate evidence, and draft a verdict. Every published claim is reviewed and approved by a human operator before appearing on the site. The goal is to verify what AI companies and products actually do, especially around environmental impact, safety practices, and transparency.",
      },
    },
    {
      "@type": "Question",
      "name": "What topics are covered?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Claims made by or about AI companies and AI products regarding environmental impact, energy use, carbon footprint, sustainability practices, safety claims, transparency disclosures, and responsible AI practices. Coverage includes any AI company or product where a verifiable claim can be evaluated against publicly accessible sources.",
      },
    },
    {
      "@type": "Question",
      "name": "What is not covered?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Financial or investment advice, legal or regulatory interpretation, non-AI technology companies, claims about individuals, claims relying solely on paywalled sources with no accessible backup, and general technology product reviews unrelated to environmental impact, energy use, sustainability, safety, or responsible AI practices.",
      },
    },
    {
      "@type": "Question",
      "name": "What methodology is used for research?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Claims move through a pipeline: (1) Research — an AI agent searches for sources. (2) Analysis — an analyst agent evaluates evidence and drafts a verdict; an auditor agent checks for consistency. (3) Human review — an operator approves, rejects, or requests revision. Nothing publishes without human sign-off. (4) Schema validation — all data is validated by Zod schemas at build time.",
      },
    },
    {
      "@type": "Question",
      "name": "How does work enter this site?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Six channels put new research in the queue: (1) A new criterion — a reusable claim template is added and the system fans out a draft claim for every applicable entity. (2) A new company or product — an operator onboards an entity and the system fans out draft claims across every active criterion. (3) A new source — the system matches it to existing criteria or claims and queues new work. (4) A topic or URL drop — free-form work added to the queue file for triage. (5) A public source submission via GitHub issue — an operator reviews and ingests if accepted. (6) A public claim request — planned, not yet live. None of these channels publish anything directly; every claim goes through the methodology pipeline before appearing on the site.",
      },
    },
    {
      "@type": "Question",
      "name": "What types of sources are used?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Sources are classified into three tiers: Primary (company disclosures, official documentation, regulatory filings), Secondary (journalism, academic papers, analyst reports), and Tertiary (advocacy, opinion, consumer guides). Every source is linked from the claim page that cites it.",
      },
    },
    {
      "@type": "Question",
      "name": "What is the content license?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Research content is published under CC-BY-4.0. Site code is MIT licensed.",
      },
    },
    {
      "@type": "Question",
      "name": "What conflicts of interest exist?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Dangerous Robot and TreadLightly AI share the same founder. Many claims here back assertions on the TreadLightly site, which shapes what gets researched. No verdict is paid, sponsored, or commissioned. The operator holds no equity, debt, or paid advisory role with the AI companies covered.",
      },
    },
  ],
};
```

**Add to the template before `</article>`:**

```astro
<script type="application/ld+json" set:html={JSON.stringify(faqSchema)} />
```

**Maintenance note:** The FAQ content is static HTML. When a new question is added to the HTML, the `faqSchema` array must be updated in the same commit. This coupling is unavoidable without a data-driven FAQ; the tradeoff is acceptable given how rarely the FAQ changes.

### 11. WebSite JSON-LD

Add to `/src/pages/index.astro`. The homepage uses `chrome="minimal"` so it doesn't render `Base.astro`'s nav, but it still renders the `<Base>` layout and its `<head>`. The WebSite schema is appropriate here because it establishes the site's identity and declares the search action.

The `potentialAction` points to `/claims?q={search_term_string}`. The claims index page already has a search bar (via `FilterBar.astro`). This schema tells Google that the site has a search function, which can produce a sitelinks searchbox in search results.

**Add to the `index.astro` frontmatter:**

```astro
const websiteSchema = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "Dangerous Robot",
  "url": "https://dangerousrobot.org",
  "description": "Open, accountable research on AI and the industries building it.",
  "potentialAction": {
    "@type": "SearchAction",
    "target": {
      "@type": "EntryPoint",
      "urlTemplate": "https://dangerousrobot.org/claims?q={search_term_string}",
    },
    "query-input": "required name=search_term_string",
  },
};
```

**Add to the template (inside or after the `<Base>` slot content):**

```astro
<script type="application/ld+json" set:html={JSON.stringify(websiteSchema)} />
```

**Note on the search URL:** The claims filter bar uses client-side JavaScript to filter results; it does not parse a `?q=` query string from the URL on load. To make the SearchAction functional (Google can submit a search and land on a useful page), the claims page would need to read `?q=` from `URLSearchParams` and apply the filter on load. That is a separate, small JS change in `FilterBar.astro` or the claims index page. Document it as a follow-up; the SearchAction schema can be added now.

### 12. Organization JSON-LD

Add to `Base.astro` so it appears on every page. This identifies the site's publisher.

**Add to `Base.astro` frontmatter (after existing destructuring):**

```astro
const orgSchema = {
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Dangerous Robot",
  "url": "https://dangerousrobot.org",
  "logo": "https://dangerousrobot.org/dr-logo.png",
  "sameAs": [
    "https://github.com/dangerous-robot/site",
  ],
};
```

**Add to `<head>` (before `</head>`):**

```astro
<script type="application/ld+json" set:html={JSON.stringify(orgSchema)} />
```

The `sameAs` array uses the GitHub repo URL. If the project acquires social media accounts, add them to this array.

### Files changed (Structured data)

| File | Change |
|------|--------|
| `src/components/Breadcrumb.astro` | add BreadcrumbList JSON-LD |
| `src/pages/claims/[...slug].astro` | add ClaimReview JSON-LD with verdict mapping; guard for draft/archived |
| `src/pages/faq/index.astro` | add FAQPage JSON-LD |
| `src/pages/index.astro` | add WebSite JSON-LD with SearchAction |
| `src/layouts/Base.astro` | add Organization JSON-LD |

---

## Milestone: Performance

**Status:** `[ ] ready to implement`

### 13. Font loading

**Current state:** `Base.astro` line 38 loads the Orbitron font via a render-blocking CDN stylesheet:

```html
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;700;800&display=swap" rel="stylesheet" />
```

The two `preconnect` hints on lines 36–37 help but do not eliminate the render block. The font is used exclusively for `--font-wordmark` (the site name in the nav and the hero wordmark). It is decorative; the content is readable without it.

**Option A: `rel="preload"` + `rel="stylesheet"` pattern**

Replace the single link with a non-blocking load pattern:

```html
<link rel="preload" as="style"
  href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;700;800&display=swap"
  onload="this.onload=null;this.rel='stylesheet'" />
<noscript>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;700;800&display=swap" />
</noscript>
```

This is a well-known pattern (loadCSS technique). The font loads asynchronously; if it arrives before first paint, the wordmark renders with Orbitron; if not, the system fallback shows first and swaps when the font loads.

Since `display=swap` is already in the Google Fonts URL, this works cleanly: `font-display: swap` is the default Google Fonts behavior, and the swap happens after the CSS loads.

Downside: The font still comes from Google's CDN. GDPR-sensitive deployments may want to self-host. Also, the async load means there will always be some FOUT (flash of unstyled text) on first visit before cache warms.

**Option B: self-host via `fontsource`**

```bash
npm install @fontsource-variable/orbitron
# or for static weights:
npm install @fontsource/orbitron
```

Import in `Base.astro` or a CSS file:

```ts
import '@fontsource/orbitron/600.css';
import '@fontsource/orbitron/700.css';
import '@fontsource/orbitron/800.css';
```

Then add `font-display: optional` in the font-face declaration (fontsource allows overriding this by importing the CSS and modifying the `@font-face` block, or by using a custom CSS layer).

Downside: Adds ~80–100KB to the npm bundle. Fontsource packages embed the font file paths; you need to verify the Astro build copies them to `dist/` correctly (it does, via Vite's asset pipeline).

**Recommendation: Option A (async CDN) now, revisit later.**

Orbitron is decorative, used only for the site name and hero wordmark. `font-display: optional` would be the ideal value (skip rendering the font if it doesn't load in the first 100ms), but it requires changing what Google Fonts sends. Google Fonts uses `swap` by default; there is no URL parameter to force `optional`.

With Option A, the behavior is effectively `swap` (not `optional`). If avoiding FOUT for a decorative font is a priority, either add a CSS override in the local `@font-face` block (which won't work if the font comes from a CDN stylesheet) or switch to Option B and set `font-display: optional` directly.

If the project moves to full GDPR compliance or eliminates third-party requests for performance, switch to Option B at that time.

**Change for Option A in `Base.astro`:**

Replace lines 36–38:

```astro
<!-- before -->
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;700;800&display=swap" rel="stylesheet" />
```

```astro
<!-- after -->
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="preload" as="style"
  href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;700;800&display=swap"
  onload="this.onload=null;this.rel='stylesheet'" />
<noscript>
  <link rel="stylesheet"
    href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;700;800&display=swap" />
</noscript>
```

Note that Astro compiles `.astro` files and `onload` on a `<link>` in the `<head>` is treated as a string attribute, not an event binding. This is correct and works in all browsers. No Astro-specific escaping is needed.

### Files changed (Performance)

| File | Change |
|------|--------|
| `src/layouts/Base.astro` | replace blocking font stylesheet link with async preload pattern |

---

## Design decisions summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| `trailingSlash` | `"never"` | Prevents `/foo` and `/foo/` duplicate-content; matches existing nav link style |
| Sitemap priority for claims | 0.9 | Claims are the primary research output; highest crawl priority |
| Sitemap priority for sources | 0.4 | Supporting material; should be found via claim pages |
| OG `og:type` | `website` for all pages | Correct for a research/reference site; `article` type requires additional schema fields |
| Default OG image | `/dr-logo.png` | Exists in `public/`; adequate fallback until a proper 1200×630 card is designed |
| Twitter card type | `summary` | Matches square logo; upgrade to `summary_large_image` when a landscape social card exists |
| ClaimReview `unverified` ratingValue | 3 | Midpoint; neither confirms nor refutes; least misleading |
| ClaimReview `n-a` ratingValue | 3 | Same reasoning as `unverified` |
| ClaimReview guard | published only | Draft and archived claims should not enter Google's fact-check index |
| Font loading | Option A (async CDN) | Decorative font; avoid blocking render; revisit for GDPR or performance tuning |
| BreadcrumbList origin | hardcoded `dangerousrobot.org` | Simpler than reading `Astro.site`; acceptable for a single-domain site |
| Organization `sameAs` | GitHub repo URL only | Only confirmed public presence; add social accounts if they are created |
| FAQPage schema | hardcoded array | FAQ content is static HTML; data-driven approach would add complexity for a rarely-changed page |
| SearchAction URL | `/claims?q={search_term_string}` | Claims is the primary search target; `?q=` parameter support is a follow-up task |
| JSON-LD escaping | no hardening applied | The data values (titles, descriptions, summaries) are controlled content with a very low chance of containing `</script>`. If arbitrary user content is ever embedded in JSON-LD, add `.replace(/</g, '\\u003c')` after `JSON.stringify`. |
| `@astrojs/sitemap` version | pin to latest `^3.x` at install time | Verify Astro 6 compatibility in `package.json` peer deps before installing; the integration major version should match the Astro 6 integration generation. |

import { defineConfig } from "astro/config";
import sitemap, { ChangeFreqEnum } from "@astrojs/sitemap";
import { unified } from "@astrojs/markdown-remark";
import { isAlphaDetailPath, INDEX_ALPHA_DETAIL_PAGES } from "./src/lib/seo";
import remarkResearchMarkup from "./src/lib/remarkResearchMarkup";

export default defineConfig({
  site: "https://dangerousrobot.org",
  trailingSlash: "always",
  // Astro 7's default ('jsx') drops whitespace between inline elements, which
  // would glue adjacent links, badges and spans together across the site.
  compressHTML: true,
  markdown: {
    // Research Markdown is LLM-written: no raw HTML, no script-scheme links.
    // Set on the processor itself; a plugin passed via `remarkPlugins` is
    // silently skipped once someone configures a processor.
    processor: unified({ remarkPlugins: [remarkResearchMarkup] }),
  },
  redirects: {
    "/faq": "/research",
    "/claims": "/research/claims",
    "/claims/[...slug]": "/research/claims/[...slug]",
    "/entities/[...slug]": "/research/entities/[...slug]",
    "/companies": "/research/companies",
    "/products": "/research/products",
    "/subjects": "/research/subjects",
    "/topics": "/research/topics",
    "/topics/[topic]": "/research/topics/[topic]",
    "/sources": "/research/sources",
    "/sources/[...slug]": "/research/sources/[...slug]",
    "/criteria": "/research/criteria",
    "/criteria/[slug]": "/research/criteria/[slug]",
    "/writing/pledge-prohibit-ai-self-improvement-pledge": "/petitions/prohibit-ai-self-improvement/",
  },
  integrations: [
    sitemap({
      changefreq: ChangeFreqEnum.WEEKLY,
      priority: 0.7,
      // Exclude alpha-stage detail pages while INDEX_ALPHA_DETAIL_PAGES is false.
      // Pages still ship with <meta name="robots" content="noindex,nofollow">,
      // but skipping them in the sitemap saves Googlebot crawl budget. They are
      // re-included when Brandon flips `INDEX_ALPHA_DETAIL_PAGES` (src/lib/seo.ts)
      // after 1.0.0.
      filter: (page) => {
        // Print-only flyer pages are noindex; the pattern matches with or without a trailing slash.
        if (/\/flyer\/?$/.test(new URL(page).pathname)) return false;
        if (INDEX_ALPHA_DETAIL_PAGES) return true;
        const pathname = new URL(page).pathname;
        return !isAlphaDetailPath(pathname);
      },
      serialize(item) {
        const path = new URL(item.url).pathname;
        // Index pages end in a slash too, so detail patterns need a segment after the prefix.
        if (/^\/research\/claims\/.+/.test(path)) {
          return { ...item, changefreq: ChangeFreqEnum.MONTHLY, priority: 0.9 };
        }
        if (
          /^\/research\/(entities|companies|products|subjects)\/.+/.test(path)
        ) {
          return { ...item, changefreq: ChangeFreqEnum.WEEKLY, priority: 0.8 };
        }
        if (path === "/research/sources/") {
          return { ...item, changefreq: ChangeFreqEnum.WEEKLY, priority: 0.5 };
        }
        if (/^\/research\/sources\/.+/.test(path)) {
          return { ...item, changefreq: ChangeFreqEnum.MONTHLY, priority: 0.4 };
        }
        if (path.startsWith("/resources/")) {
          return { ...item, changefreq: ChangeFreqEnum.MONTHLY, priority: 0.7 };
        }
        return { ...item, changefreq: ChangeFreqEnum.WEEKLY, priority: 0.7 };
      },
    }),
  ],
});

import { defineConfig } from "astro/config";
import sitemap, { ChangeFreqEnum } from "@astrojs/sitemap";
import { isAlphaDetailPath, INDEX_ALPHA_DETAIL_PAGES } from "./src/lib/seo";

export default defineConfig({
  site: "https://dangerousrobot.org",
  trailingSlash: "never",
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
    "/writing/pledge-prohibit-ai-self-improvement-pledge": "/petitions/prohibit-ai-self-improvement",
  },
  integrations: [
    sitemap({
      changefreq: ChangeFreqEnum.WEEKLY,
      priority: 0.7,
      // Exclude alpha-stage detail pages while INDEX_ALPHA_DETAIL_PAGES is false.
      // Pages still ship with <meta name="robots" content="noindex,nofollow">,
      // but skipping them in the sitemap saves Googlebot crawl budget. Flip the
      // flag in src/lib/seo.ts when alpha ends to re-include them.
      filter: (page) => {
        if (INDEX_ALPHA_DETAIL_PAGES) return true;
        const pathname = new URL(page).pathname;
        return !isAlphaDetailPath(pathname);
      },
      serialize(item) {
        if (item.url.includes("/research/claims/")) {
          return { ...item, changefreq: ChangeFreqEnum.MONTHLY, priority: 0.9 };
        }
        if (
          item.url.includes("/research/entities/") ||
          item.url.includes("/research/companies/") ||
          item.url.includes("/research/products/") ||
          item.url.includes("/research/subjects/")
        ) {
          return { ...item, changefreq: ChangeFreqEnum.WEEKLY, priority: 0.8 };
        }
        if (item.url === "https://dangerousrobot.org/research/sources") {
          return { ...item, changefreq: ChangeFreqEnum.WEEKLY, priority: 0.5 };
        }
        if (item.url.includes("/research/sources/")) {
          return { ...item, changefreq: ChangeFreqEnum.MONTHLY, priority: 0.4 };
        }
        if (item.url.includes("/resources/") || item.url.endsWith("/resources")) {
          return { ...item, changefreq: ChangeFreqEnum.MONTHLY, priority: 0.7 };
        }
        return { ...item, changefreq: ChangeFreqEnum.WEEKLY, priority: 0.7 };
      },
    }),
  ],
});

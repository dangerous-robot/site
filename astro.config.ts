import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import { isAlphaDetailPath, INDEX_ALPHA_DETAIL_PAGES } from "./src/lib/seo";

export default defineConfig({
  site: "https://dangerousrobot.org",
  trailingSlash: "never",
  integrations: [
    sitemap({
      changefreq: "weekly",
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
        if (item.url.includes("/claims/")) {
          return { ...item, changefreq: "monthly", priority: 0.9 };
        }
        if (item.url.includes("/entities/") || item.url.includes("/companies/") || item.url.includes("/products/")) {
          return { ...item, changefreq: "weekly", priority: 0.8 };
        }
        if (item.url === "https://dangerousrobot.org/sources") {
          return { ...item, changefreq: "weekly", priority: 0.5 };
        }
        if (item.url.includes("/sources/")) {
          return { ...item, changefreq: "monthly", priority: 0.4 };
        }
        return { ...item, changefreq: "weekly", priority: 0.7 };
      },
    }),
  ],
});

import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://dangerousrobot.org",
  trailingSlash: "never",
  integrations: [
    sitemap({
      changefreq: "weekly",
      priority: 0.7,
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

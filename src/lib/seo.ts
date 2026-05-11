/**
 * SEO indexing controls for alpha-stage detail pages.
 *
 * The site is in alpha. Detail pages under /research/claims/{entity}/{claim},
 * /research/sources/{yyyy}/{slug}, and /research/entities/{type}/{slug} are generated
 * from AI agent research and may be incomplete or wrong. We do not
 * want them in the search index until the content stabilizes.
 *
 * Flip the flag below to true (and rebuild + redeploy) when alpha ends
 * to make these pages indexable and re-include them in the sitemap.
 *
 * URLs are stable across the flip. Already-published pages remain
 * accessible at the same paths; the only thing that changes is the
 * `<meta name="robots">` tag and sitemap inclusion.
 */
export const INDEX_ALPHA_DETAIL_PAGES = false as boolean;

/**
 * Patterns that match agent-generated detail pages. Anchored to be
 * exact: list/index pages like /research/claims and /research/sources
 * do NOT match.
 *
 * - /research/claims/{entity}/{claim}
 * - /research/sources/{yyyy}/{slug}
 * - /research/entities/{anything-after}
 */
const ALPHA_DETAIL_PATTERNS: readonly RegExp[] = [
  /^\/research\/claims\/[^/]+\/[^/]+\/?$/,
  /^\/research\/sources\/\d{4}\/[^/]+\/?$/,
  /^\/research\/entities\/.+/,
];

/** True when `pathname` is an alpha-stage detail page. */
export function isAlphaDetailPath(pathname: string): boolean {
  return ALPHA_DETAIL_PATTERNS.some((rx) => rx.test(pathname));
}

/** True when the page should emit `noindex,nofollow`. */
export function shouldNoindex(pathname: string): boolean {
  return !INDEX_ALPHA_DETAIL_PAGES && isAlphaDetailPath(pathname);
}

/** True when the page should be included in the sitemap. */
export function shouldIncludeInSitemap(pathname: string): boolean {
  return INDEX_ALPHA_DETAIL_PAGES || !isAlphaDetailPath(pathname);
}

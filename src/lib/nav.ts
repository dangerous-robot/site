export type NavLink = { href: string; label: string; external?: boolean };
/** `primary: false` keeps a section's sub-nav on its own pages but leaves it out of the top row and the dropdown. */
export type Section = { href: string; label: string; links: NavLink[]; primary?: false };

/** The site nav. Base.astro renders it on every standard-chrome page; the homepage menu takes its short labels from here. */
export const SECTIONS: Section[] = [
  {
    href: '/research',
    label: 'Research',
    // Out of the primary nav until the research pages are reworked.
    primary: false,
    links: [
      { href: '/research/topics',      label: 'Topics' },
      { href: '/research/claims',      label: 'Claims' },
      { href: '/research/companies',   label: 'Companies' },
      { href: '/research/products',    label: 'Products' },
    ],
  },
  {
    href: '/resources',
    label: 'Resources',
    links: [
      { href: '/resources/ai-safety',      label: 'AI Safety Index' },
      { href: '/resources/responsible-ai', label: 'Responsible AI' },
    ],
  },
  { href: '/writing', label: 'Writing', links: [] },
  { href: '/about',   label: 'About',   links: [] },
];

/** The sections the top row and the collapsed dropdown list. Both derive from this, so they list the same pages. */
export const PRIMARY_SECTIONS: Section[] = SECTIONS.filter((s) => s.primary !== false);

export const TOP_LINKS: NavLink[] = PRIMARY_SECTIONS.map(({ href, label }) => ({ href, label }));

/** Footer links, one row. Credits, GitHub and the version live on the About page. */
export const FOOTER_LINKS: NavLink[] = [
  { href: '/about',                label: 'About' },
  { href: '/values',               label: 'Values' },
  { href: '/research#methodology', label: 'Methodology' },
  { href: 'https://creativecommons.org/licenses/by/4.0/', label: 'CC-BY-4.0', external: true },
];

/** The nav label for an href, searching the top row, section links, then the footer. */
export function navLabel(href: string): string | undefined {
  const all = [...TOP_LINKS, ...SECTIONS.flatMap((s) => s.links), ...FOOTER_LINKS];
  return all.find((l) => l.href === href)?.label;
}

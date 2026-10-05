export type NavLink = { href: string; label: string; external?: boolean };
export type Section = { href: string; label: string; links: NavLink[] };

/** The site nav. Base.astro renders it on every standard-chrome page; the homepage menu takes its short labels from here. */
export const SECTIONS: Section[] = [
  {
    href: '/research',
    label: 'Research',
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
      { href: '/resources/should-i',       label: 'Should I Use AI?' },
      { href: '/resources/ai-safety',      label: 'AI Safety Index' },
      { href: '/resources/turn-off-ai',    label: 'Turn Off AI' },
      { href: '/resources/responsible-ai', label: 'Responsible AI' },
    ],
  },
  { href: '/writing', label: 'Writing', links: [] },
  { href: '/about',   label: 'About',   links: [] },
];

/** Derived from SECTIONS: the collapsed dropdown renders SECTIONS, so the two must list the same pages. */
export const TOP_LINKS: NavLink[] = SECTIONS.map(({ href, label }) => ({ href, label }));

/** Footer links. Internal links share the first row; external ones share the second, with the version. */
export const FOOTER_LINKS: NavLink[] = [
  { href: '/about',                label: 'About' },
  { href: '/values',               label: 'Values' },
  { href: '/research#methodology', label: 'Methodology' },
  { href: '/credits',              label: 'Credits' },
  { href: 'https://github.com/dangerous-robot/site',         label: 'GitHub',    external: true },
  { href: 'https://creativecommons.org/licenses/by/4.0/',    label: 'CC-BY-4.0', external: true },
];

/** The nav label for an href, searching the top row, section links, then the footer. */
export function navLabel(href: string): string | undefined {
  const all = [...TOP_LINKS, ...SECTIONS.flatMap((s) => s.links), ...FOOTER_LINKS];
  return all.find((l) => l.href === href)?.label;
}

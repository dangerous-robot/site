import type { CollectionEntry } from 'astro:content';

type ResourceEntry = CollectionEntry<'resources'>;

const SITE_ORIGIN = 'https://dangerousrobot.org';
const ORG = { '@type': 'Organization', name: 'Dangerous Robot' } as const;

/**
 * Walks any nested structure and collects every value found at keys named
 * `last_verified` or `last_checked`. Returns the max parsable date as ISO, or
 * undefined if none found.
 */
function collectFreshestDate(value: unknown): string | undefined {
  const dates: number[] = [];

  function walk(v: unknown, parentKey?: string): void {
    if (v == null) return;
    if (Array.isArray(v)) {
      for (const item of v) walk(item);
      return;
    }
    if (typeof v === 'object') {
      for (const [k, child] of Object.entries(v as Record<string, unknown>)) {
        walk(child, k);
      }
      return;
    }
    if (parentKey === 'last_verified' || parentKey === 'last_checked') {
      const t = v instanceof Date ? v.getTime() : new Date(String(v)).getTime();
      if (!Number.isNaN(t)) dates.push(t);
    }
  }

  walk(value);
  if (dates.length === 0) return undefined;
  return new Date(Math.max(...dates)).toISOString();
}

interface PlatformSubSection {
  title?: string;
  steps?: string[];
}

interface Platform {
  name?: string;
  context?: string;
  where_it_shows?: string;
  steps?: string[];
  sub_sections?: PlatformSubSection[];
}

interface MatrixProduct {
  key?: string;
  name?: string;
  url?: string;
}

function buildHowToSections(platforms: Platform[]): Record<string, unknown>[] {
  return platforms.map((platform) => {
    const stepEntries: Record<string, unknown>[] = [];

    if (Array.isArray(platform.sub_sections) && platform.sub_sections.length > 0) {
      for (const sub of platform.sub_sections) {
        const steps = Array.isArray(sub.steps) ? sub.steps : [];
        for (const text of steps) {
          stepEntries.push({
            '@type': 'HowToStep',
            name: sub.title || platform.name || 'Step',
            text,
          });
        }
      }
    } else if (Array.isArray(platform.steps)) {
      for (const text of platform.steps) {
        stepEntries.push({ '@type': 'HowToStep', text });
      }
    }

    const section: Record<string, unknown> = {
      '@type': 'HowToSection',
      name: platform.name,
      itemListElement: stepEntries,
    };
    if (platform.context) section.description = platform.context;
    return section;
  });
}

function buildMatrixItemList(products: MatrixProduct[]): Record<string, unknown> {
  return {
    '@type': 'ItemList',
    itemListElement: products.map((product, i) => {
      const item: Record<string, unknown> = {
        '@type': 'ListItem',
        position: i + 1,
        name: product.name,
      };
      if (product.url) item.url = product.url;
      return item;
    }),
  };
}

export function buildResourceSchema(entry: ResourceEntry): Record<string, unknown> {
  const { title, description, layout, pubDate } = entry.data;
  const data = entry.data.data as Record<string, unknown> | undefined;

  const url = `${SITE_ORIGIN}/resources/${entry.id}`;
  const datePublished = pubDate.toISOString();
  const dateModified = collectFreshestDate(data) ?? datePublished;

  const base: Record<string, unknown> = {
    '@context': 'https://schema.org',
    headline: title,
    description,
    url,
    datePublished,
    dateModified,
    author: { ...ORG },
    publisher: { ...ORG },
  };

  switch (layout) {
    case 'tool': {
      return {
        ...base,
        '@type': 'WebApplication',
        name: title,
        applicationCategory: 'BusinessApplication',
        browserRequirements: 'Requires JavaScript',
        operatingSystem: 'Any',
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
      };
    }

    case 'guide': {
      const platforms = Array.isArray(data?.platforms) ? (data!.platforms as Platform[]) : [];
      return {
        ...base,
        '@type': 'HowTo',
        name: title,
        mainEntityOfPage: url,
        step: buildHowToSections(platforms),
      };
    }

    case 'matrix': {
      const products = Array.isArray(data?.products) ? (data!.products as MatrixProduct[]) : [];
      return {
        ...base,
        '@type': 'Article',
        mainEntityOfPage: url,
        mainEntity: buildMatrixItemList(products),
      };
    }

    case 'article':
    default: {
      const article: Record<string, unknown> = {
        ...base,
        '@type': 'Article',
        mainEntityOfPage: url,
      };
      if (entry.id === 'ai-safety') {
        article.about = { '@type': 'Thing', name: 'FLI AI Safety Index' };
      }
      return article;
    }
  }
}

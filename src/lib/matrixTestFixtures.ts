// Shared fixtures for the matrix unit tests. Not a test file itself (no
// `.test` in the name), so the test glob skips it.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';
import yaml from 'js-yaml';
import type { CriterionInfo } from './matrixCheck';
import type { ClaimInfo, SourceInfo } from './matrixEvidence';

export const REVIEWER = 'brandon@dangerousrobot.org';

export function claim(over: Partial<ClaimInfo> = {}): ClaimInfo {
  return {
    id: 'greenpt/renewable-energy-hosting',
    title: 'GreenPT is hosted on renewable energy',
    entity: 'products/greenpt',
    status: 'published',
    verdict: 'true',
    confidence: 'high',
    as_of: new Date('2026-09-28'),
    criteria_slug: 'renewable-energy-hosting',
    reviewer: REVIEWER,
    ...over,
  };
}

const PAGE = new URL('../content/resources/responsible-ai.md', import.meta.url);
const TEMPLATES = new URL('../../research/templates.yaml', import.meta.url);

/** The page's `data:` payload, a fresh copy each call: gray-matter caches parses made with no options. */
export function pageData(): unknown {
  return (matter(readFileSync(PAGE, 'utf-8'), {}).data as { data: unknown }).data;
}

const SOURCES_DIR = fileURLToPath(new URL('../../research/sources/', import.meta.url));

/** Every source file under research/sources, keyed by id (`<yyyy>/<slug>`), as the lookups want them. */
export function researchSources(): Map<string, SourceInfo> {
  const out = new Map<string, SourceInfo>();
  for (const year of readdirSync(SOURCES_DIR)) {
    const dir = join(SOURCES_DIR, year);
    if (!statSync(dir).isDirectory()) continue;
    for (const file of readdirSync(dir)) {
      if (!file.endsWith('.md')) continue;
      const id = `${year}/${file.slice(0, -3)}`;
      const data = matter(readFileSync(join(dir, file), 'utf-8'), {}).data as Record<string, unknown>;
      out.set(id, {
        id,
        title: String(data.title),
        publisher: String(data.publisher),
        accessed_date: new Date(String(data.accessed_date)),
        archived_url: data.archived_url ? String(data.archived_url) : undefined,
      });
    }
  }
  return out;
}

/** The active criteria from research/templates.yaml, as the check's lookups want them. */
export function activeCriteria(): Map<string, CriterionInfo> {
  const { templates } = yaml.load(readFileSync(TEMPLATES, 'utf-8')) as { templates: { slug: string; vocabulary?: Record<string, string[]> }[] };
  return new Map(templates.map((t) => [t.slug, { vocabulary: t.vocabulary }]));
}

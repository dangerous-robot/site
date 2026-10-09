// Shared fixtures for the matrix unit tests. Not a test file itself (no
// `.test` in the name), so the test glob skips it.
import { readFileSync } from 'node:fs';
import matter from 'gray-matter';
import type { ClaimInfo } from './matrixEvidence';

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

/** The page's `data:` payload, a fresh copy each call: gray-matter caches parses made with no options. */
export function pageData(): unknown {
  return (matter(readFileSync(PAGE, 'utf-8'), {}).data as { data: unknown }).data;
}

import type { CollectionEntry } from 'astro:content';

export interface ClaimEntry {
  id: string;
  slug: string;
  title: string;
  verdict: string;
  entity: string;
  category: string;
  standard_slug?: string;
}

export interface StandardsMiss {
  claimId: string;
  reason: string;
}

/** Build a map: standardSlug → entityId → ClaimEntry[] */
export function buildStandardsIndex(
  claims: CollectionEntry<'claims'>[],
): Map<string, Map<string, ClaimEntry[]>> {
  const index = new Map<string, Map<string, ClaimEntry[]>>();

  for (const claim of claims) {
    const standardSlug =
      claim.data.standard_slug ?? stemFromId(claim.id);
    if (!standardSlug) continue;

    const entityId = claim.data.entity;
    if (!index.has(standardSlug)) index.set(standardSlug, new Map());
    const byEntity = index.get(standardSlug)!;
    if (!byEntity.has(entityId)) byEntity.set(entityId, []);
    byEntity.get(entityId)!.push({
      id: claim.id,
      slug: claim.id,
      title: claim.data.title,
      verdict: claim.data.verdict,
      entity: claim.data.entity,
      category: claim.data.category,
      standard_slug: claim.data.standard_slug,
    });
  }

  return index;
}

/** Extract the filename stem from an id like "anthropic/publishes-sustainability-report" */
function stemFromId(id: string): string {
  return id.split('/').pop() ?? id;
}

export function logDerivationMisses(misses: StandardsMiss[]): void {
  for (const miss of misses) {
    console.warn(`[standards] ${miss.claimId}: ${miss.reason}`);
  }
}

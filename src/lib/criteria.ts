import type { CollectionEntry } from 'astro:content';

export interface ClaimEntry {
  id: string;
  slug: string;
  title: string;
  verdict: string;
  entity: string;
  topics: string[];
  criteria_slug?: string;
}

export interface CriteriaMiss {
  claimId: string;
  reason: string;
}

/** Build a map: criteriaSlug → entityId → ClaimEntry[] */
export function buildCriteriaIndex(
  claims: CollectionEntry<'claims'>[],
): Map<string, Map<string, ClaimEntry[]>> {
  const index = new Map<string, Map<string, ClaimEntry[]>>();

  for (const claim of claims) {
    const criteriaSlug =
      claim.data.criteria_slug ?? stemFromId(claim.id);
    if (!criteriaSlug) continue;

    const entityId = claim.data.entity;
    if (!index.has(criteriaSlug)) index.set(criteriaSlug, new Map());
    const byEntity = index.get(criteriaSlug)!;
    if (!byEntity.has(entityId)) byEntity.set(entityId, []);
    byEntity.get(entityId)!.push({
      id: claim.id,
      slug: claim.id,
      title: claim.data.title,
      verdict: claim.data.verdict,
      entity: claim.data.entity,
      topics: claim.data.topics,
      criteria_slug: claim.data.criteria_slug,
    });
  }

  return index;
}

/** Extract the filename stem from an id like "anthropic/publishes-sustainability-report" */
function stemFromId(id: string): string {
  return id.split('/').pop() ?? id;
}

export function logDerivationMisses(misses: CriteriaMiss[]): void {
  for (const miss of misses) {
    console.warn(`[criteria] ${miss.claimId}: ${miss.reason}`);
  }
}

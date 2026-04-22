import type { CollectionEntry } from 'astro:content';
import type { ClaimEntry } from './standards';

/** Build a map: sourceId → ClaimEntry[] */
export function buildCitationIndex(
  claims: CollectionEntry<'claims'>[],
): Map<string, ClaimEntry[]> {
  const index = new Map<string, ClaimEntry[]>();

  for (const claim of claims) {
    const sources: string[] = claim.data.sources ?? [];
    for (const sourceId of sources) {
      if (!index.has(sourceId)) index.set(sourceId, []);
      index.get(sourceId)!.push({
        id: claim.id,
        slug: claim.id,
        title: claim.data.title,
        verdict: claim.data.verdict,
        entity: claim.data.entity,
        category: claim.data.category,
        standard_slug: claim.data.standard_slug,
      });
    }
  }

  return index;
}

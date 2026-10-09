// Turns the research collections into the plain lookups the matrix evidence
// rules read. Type-only Astro import, so nothing here needs the Astro runtime.
import type { CollectionEntry } from 'astro:content';
import type { CheckLookups } from './matrixCheck';

export function buildMatrixLookups(
  claims: CollectionEntry<'claims'>[],
  sources: CollectionEntry<'sources'>[],
  entities: CollectionEntry<'entities'>[],
  criteria: CollectionEntry<'criteria'>[],
  valuesPositions: string[],
): CheckLookups {
  return {
    claims: new Map(claims.map((c) => [c.id, {
      id: c.id,
      title: c.data.title,
      entity: c.data.entity,
      status: c.data.status,
      verdict: c.data.verdict,
      confidence: c.data.confidence,
      as_of: c.data.as_of,
      criteria_slug: c.data.criteria_slug,
      reviewer: c.data.audit?.human_review.reviewer ?? null,
    }])),
    sources: new Map(sources.map((s) => [s.id, {
      id: s.id,
      title: s.data.title,
      publisher: s.data.publisher,
      accessed_date: s.data.accessed_date,
      archived_url: s.data.archived_url,
    }])),
    entities: new Map(entities.map((e) => [e.id, { parent_company: e.data.parent_company }])),
    criteria: new Map(criteria.map((c) => [c.data.slug, { vocabulary: c.data.vocabulary }])),
    valuesPositions,
  };
}

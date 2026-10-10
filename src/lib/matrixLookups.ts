// Turns the research collections into the plain lookups the matrix evidence
// rules read. The only matrix module that touches the Astro runtime.
import { getCollection, type CollectionEntry } from 'astro:content';
import type { CheckLookups } from './matrixCheck';
import { VALUES_POSITION_IDS } from './valuesPositions';

/** The lookups for the matrix page: every claim, source, entity and criterion, and the Values position ids. */
export async function loadMatrixLookups(): Promise<CheckLookups> {
  const [claims, sources, entities, criteria] = await Promise.all([
    getCollection('claims'),
    getCollection('sources'),
    getCollection('entities'),
    getCollection('criteria'),
  ]);
  return buildMatrixLookups(claims, sources, entities, criteria, VALUES_POSITION_IDS);
}

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

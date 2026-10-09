// The build check for the Responsible AI matrix (plan § Design "The build
// check"). Collects every problem and throws once, so one build run reports
// them all. Plain types only, so the tests run under tsx.

import {
  citedId,
  isCapped,
  isReviewedClaim,
  rowKind,
  verdictAgrees,
  type EvidenceLookups,
  type MatrixDataLike,
  type ProductRef,
} from './matrixEvidence';
import { VALUES_PATH_PREFIX, type MatrixCell, type MatrixFeature, type MatrixFootnote, type SummaryEntry, type SummaryField } from './matrixSchema';

export interface EntityInfo {
  parent_company?: string;
}

export interface CriterionInfo {
  vocabulary?: Record<string, string[]>;
}

export interface CheckLookups extends EvidenceLookups {
  entities: Map<string, EntityInfo>;
  criteria: Map<string, CriterionInfo>;
  /** Ids of the Values position headings an `ideal.position` may point at. */
  valuesPositions: string[];
}

export interface MatrixDataForCheck extends MatrixDataLike {
  products: (ProductRef & { summary?: Partial<Record<SummaryField, SummaryEntry>> })[];
  footnotes?: MatrixFootnote[];
}

/** Lowercase, hyphens as spaces: "B-corp" matches "B Corp" in a claim title. */
function normalizeWord(s: string): string {
  return s.toLowerCase().replace(/-/g, ' ');
}

/** The vocabulary word a claim title resolves to, or null when it names none or several. */
export function vocabularyWordInTitle(title: string, vocabulary: string[]): string | null {
  const t = ` ${normalizeWord(title)} `;
  const found = vocabulary.filter((w) => t.includes(` ${normalizeWord(w)} `));
  return found.length === 1 ? found[0] : null;
}

/** Every problem with the page's citations; an empty list means the data passes. */
export function matrixEvidenceProblems(data: MatrixDataForCheck, lookups: CheckLookups): string[] {
  const problems: string[] = [];
  const allKeys = new Set(data.products.map((p) => p.key));
  const active = data.products.filter((p) => p.status === 'active');

  const checkSources = (paths: string[] | undefined, where: string) => {
    for (const path of paths ?? []) {
      const id = citedId(path, 'source');
      if (!id || !lookups.sources.has(id)) problems.push(`${where}: source "${path}" does not exist`);
    }
  };

  const criterionVocabulary = (feature: MatrixFeature): string[] | null => {
    const criterion = feature.criterion ? lookups.criteria.get(feature.criterion) : undefined;
    const vocabulary = criterion?.vocabulary ? Object.values(criterion.vocabulary).flat() : [];
    return vocabulary.length > 0 ? vocabulary : null;
  };

  const checkClaim = (cell: MatrixCell, product: ProductRef, feature: MatrixFeature, vocabulary: string[] | null, where: string) => {
    const path = cell.claim!;
    if (!feature.criterion) problems.push(`${where}: cites a claim, but the row has no criterion`);
    if (isCapped(product)) problems.push(`${where}: cites a claim, but ${product.name} is capped at the Source tier`);
    const claim = lookups.claims.get(citedId(path, 'claim') ?? '');
    if (!claim) {
      problems.push(`${where}: claim "${path}" does not exist`);
      return;
    }
    if (!isReviewedClaim(claim)) {
      problems.push(claim.status !== 'published'
        ? `${where}: claim "${path}" is ${claim.status}, not published`
        : `${where}: claim "${path}" has no reviewer who maps to a person`);
    }
    if (feature.criterion && claim.criteria_slug !== feature.criterion) {
      problems.push(`${where}: claim "${path}" is under criterion "${claim.criteria_slug ?? 'none'}", the row's is "${feature.criterion}"`);
    }
    if (!product.entity) problems.push(`${where}: cites a claim, but ${product.name} has no entity`);
    else {
      const parent = lookups.entities.get(product.entity)?.parent_company;
      if (claim.entity !== product.entity && claim.entity !== parent) {
        problems.push(`${where}: claim "${path}" is about "${claim.entity}", not ${product.name}'s entity or parent company`);
      }
    }
    if (rowKind(feature) === 'ownership') {
      if (claim.verdict !== 'true' && claim.verdict !== 'mostly-true') {
        problems.push(`${where}: ownership claim "${path}" is ${claim.verdict}; only true or mostly-true can back a structure`);
      }
      const word = vocabulary ? vocabularyWordInTitle(claim.title, vocabulary) : null;
      if (cell.term && word !== cell.term) {
        problems.push(`${where}: claim title "${claim.title}" names "${word ?? 'no vocabulary word'}", the cell's term is "${cell.term}"`);
      }
    } else if (!verdictAgrees(claim.verdict, cell.type, feature.polarity)) {
      problems.push(`${where}: verdict ${claim.verdict} does not allow the answer "${cell.type}" (polarity ${feature.polarity})`);
    }
  };

  for (const feature of data.features) {
    const row = feature.key;
    const kind = rowKind(feature);
    const ideal = feature.ideal;

    if (feature.criterion && !lookups.criteria.has(feature.criterion)) {
      problems.push(`${row}: criterion "${feature.criterion}" does not exist`);
    }
    if (ideal) {
      checkSources(ideal.sources, `${row}: stance`);
      if (ideal.position && !lookups.valuesPositions.includes(ideal.position.slice(VALUES_PATH_PREFIX.length))) {
        problems.push(`${row}: stance position "${ideal.position}" is not a Values position`);
      }
    }
    const largeModels = ideal && 'large_models' in ideal ? ideal.large_models : undefined;
    const terms = ideal && 'terms' in ideal ? ideal.terms : undefined;
    const vocabulary = terms ? criterionVocabulary(feature) : null;

    if (largeModels) {
      checkSources(largeModels.sources, `${row}: large_models`);
      for (const name of largeModels.large) {
        if (largeModels.not_large.includes(name)) problems.push(`${row}: "${name}" is in both large and not_large`);
      }
    }
    if (terms) {
      if (!vocabulary) problems.push(`${row}: ownership row needs a criterion with a vocabulary`);
      else {
        const listed = [...terms.good, ...terms.mixed, ...terms.bad];
        const repeated = listed.filter((w, i) => listed.indexOf(w) !== i);
        const missing = vocabulary.filter((w) => !listed.includes(w));
        const unknown = listed.filter((w) => !vocabulary.includes(w));
        if (missing.length || unknown.length || repeated.length) {
          const bad = [...unknown, ...repeated].join(', ') || 'none';
          problems.push(`${row}: terms must list each vocabulary word exactly once (missing: ${missing.join(', ') || 'none'}; unknown or repeated: ${bad})`);
        }
      }
    }

    for (const key of Object.keys(feature.cells)) {
      if (!allKeys.has(key)) problems.push(`${row}/${key}: cell for a key that is no product`);
    }

    for (const product of active) {
      const where = `${row}/${product.key}`;
      const cell = feature.cells[product.key];
      if (!cell) {
        problems.push(`${where}: no cell for an active product`);
        continue;
      }
      if (feature.answers && !feature.answers.includes(cell.type)) {
        problems.push(`${where}: answer "${cell.type}" is not one of the row's answers (${feature.answers.join(', ')})`);
      }
      if (kind !== 'models' && cell.models) problems.push(`${where}: "models" belongs on the models row only`);
      if (kind !== 'ownership' && (cell.term || cell.owned_by)) problems.push(`${where}: "term" and "owned_by" belong on the ownership row only`);
      if (largeModels) {
        for (const name of cell.models ?? []) {
          if (!largeModels.large.includes(name) && !largeModels.not_large.includes(name)) {
            problems.push(`${where}: model "${name}" is in neither large_models list`);
          }
        }
      }
      if (kind === 'ownership') {
        if (!cell.term) problems.push(`${where}: ownership cell has no term`);
        else if (vocabulary && !vocabulary.includes(cell.term)) problems.push(`${where}: term "${cell.term}" is not in the criterion's vocabulary`);
        checkSources(cell.owned_by?.sources, `${where}: owned_by`);
      }
      checkSources(cell.sources, where);
      if (cell.claim) checkClaim(cell, product, feature, vocabulary, where);
    }
  }

  for (const product of active) {
    for (const [field, entry] of Object.entries(product.summary ?? {})) {
      if (typeof entry !== 'string') checkSources(entry.sources, `summary.${field}/${product.key}`);
    }
  }
  (data.footnotes ?? []).forEach((note, i) => checkSources(note.sources, `footnotes[${i}] (${note.subject})`));

  return problems;
}

/** Fails the build on any bad citation; called right after the schema parse. */
export function validateMatrixEvidence(data: MatrixDataForCheck, lookups: CheckLookups): void {
  const problems = matrixEvidenceProblems(data, lookups);
  if (problems.length > 0) {
    throw new Error(`Responsible AI matrix evidence check failed:\n- ${problems.join('\n- ')}`);
  }
}

import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  matrixEvidenceProblems,
  validateMatrixEvidence,
  vocabularyWordInTitle,
  type CheckLookups,
  type MatrixDataForCheck,
} from './matrixCheck';
import type { ClaimInfo } from './matrixEvidence';
import { matrixDataSchema, type MatrixFeature } from './matrixSchema';
import { activeCriteria, claim, pageData, researchSources } from './matrixTestFixtures';

const VOCABULARY = ['publicly-traded', 'privately-held', 'non-profit', 'B-corp', 'employee-owned', 'steward-ownership', 'cooperative'];

const HOSTING = '/research/claims/greenpt/renewable-energy-hosting';
const STRUCTURE = '/research/claims/greenpt-co/corporate-structure';
const SRC = '/research/sources/2026/a';

const structureClaim = claim({
  id: 'greenpt-co/corporate-structure',
  title: 'GreenPT BV has a privately-held corporate structure',
  entity: 'companies/greenpt-co',
  criteria_slug: 'corporate-structure',
});

/** The default lookups with one claim added or replaced. */
function withClaim(c: ClaimInfo): CheckLookups {
  const l = lookups();
  l.claims.set(c.id, c);
  return l;
}

function lookups(over: Partial<CheckLookups> = {}): CheckLookups {
  return {
    claims: new Map([[claim().id, claim()], [structureClaim.id, structureClaim]]),
    sources: new Map([['2026/a', { id: '2026/a', title: 'A', publisher: 'A Co', accessed_date: new Date('2026-09-30') }]]),
    entities: new Map([['products/greenpt', { id: 'products/greenpt', parent_company: 'companies/greenpt-co' }]]),
    criteria: new Map([
      ['renewable-energy-hosting', { slug: 'renewable-energy-hosting' }],
      ['no-training-on-user-data', { slug: 'no-training-on-user-data' }],
      ['corporate-structure', { slug: 'corporate-structure', vocabulary: { STRUCTURE: VOCABULARY } }],
    ]),
    valuesPositions: ['ai-is-fueling-environmental-destruction'],
    ...over,
  };
}

/** A passing fixture: one row of each kind, two products, every citation resolving. */
function fixture(): MatrixDataForCheck {
  const features: MatrixFeature[] = [
    {
      key: 'renewable-hosting', label: 'Hosted on renewable energy', group: 'environmental', polarity: 'same',
      criterion: 'renewable-energy-hosting',
      ideal: { value: 'yes', sources: [SRC], position: '/values#ai-is-fueling-environmental-destruction' },
      cells: { greenpt: { type: 'yes', claim: HOSTING }, treadlightly: { type: 'partial', sources: [SRC] } },
    },
    {
      key: 'data-used-for-training', label: 'Data used for training', group: 'privacy-data', polarity: 'inverted',
      criterion: 'no-training-on-user-data',
      ideal: { value: 'no' },
      cells: { greenpt: { type: 'no' }, treadlightly: { type: 'no', last_checked: '2026-10-01' } },
    },
    {
      key: 'models', label: 'Models', group: 'models-safety', polarity: 'same',
      ideal: { answer: 'no large models', large_models: { sources: [SRC], large: ['Claude Opus'], not_large: ['Claude Sonnet'] } },
      cells: { greenpt: { type: 'text', detail: 'Claude Sonnet', models: ['Claude Sonnet'] }, treadlightly: { type: 'text', detail: 'GPT' } },
    },
    {
      key: 'corporate-structure', label: 'Ownership structure', group: 'business', polarity: 'same',
      criterion: 'corporate-structure',
      ideal: {
        answer: 'non-profit or similar',
        terms: { good: ['non-profit', 'steward-ownership', 'cooperative', 'B-corp', 'employee-owned'], mixed: ['privately-held'], bad: ['publicly-traded'] },
      },
      cells: {
        greenpt: { type: 'text', detail: 'Private', term: 'privately-held', claim: STRUCTURE },
        treadlightly: { type: 'text', detail: 'Sole proprietorship', term: 'privately-held', owned_by: { name: 'Owner', kind: 'publicly-traded', sources: [SRC] } },
      },
    },
    {
      key: 'accessibility', label: 'Accessibility', group: 'product-access', polarity: 'same',
      answers: ['yes', 'partial', 'unknown'],
      ideal: { value: 'yes' },
      cells: { greenpt: { type: 'partial' }, treadlightly: { type: 'unknown' } },
    },
    {
      key: 'free-tier', label: 'Free tier', group: 'business', polarity: 'same',
      cells: { greenpt: { type: 'yes', sources: [SRC] }, treadlightly: { type: 'yes' } },
    },
  ];
  return {
    products: [
      { key: 'greenpt', name: 'GreenPT', status: 'active', entity: 'products/greenpt', summary: { environmental: { text: 'Hosted at Scaleway.', sources: [SRC] } } },
      { key: 'treadlightly', name: 'TreadLightlyAI', status: 'active', max_tier: 'source', summary: { notes: 'Beta.' } },
      { key: 'gone', name: 'Gone', status: 'excluded' },
    ],
    features,
    footnotes: [{ subject: 'A note', text: 'Text.', sources: [SRC] }],
  };
}

function row(data: MatrixDataForCheck, key: string): MatrixFeature {
  return data.features.find((f) => f.key === key)!;
}

/** Runs the check on a mutated fixture and asserts exactly the expected problem, naming row and product. */
function expectProblem(mutate: (d: MatrixDataForCheck) => void, where: string, fragment: string, l: CheckLookups = lookups()) {
  const data = fixture();
  mutate(data);
  const problems = matrixEvidenceProblems(data, l);
  assert.equal(problems.length, 1, `expected one problem, got:\n${problems.join('\n')}`);
  assert.ok(problems[0].startsWith(`${where}:`), `expected "${where}:" prefix in "${problems[0]}"`);
  assert.ok(problems[0].includes(fragment), `expected "${fragment}" in "${problems[0]}"`);
}

describe('matrixEvidenceProblems: passing data', () => {
  test('the fixture passes', () => {
    assert.deepEqual(matrixEvidenceProblems(fixture(), lookups()), []);
  });
  test("today's page data passes against the real criteria and every source file on disk, with no claims", () => {
    const data = matrixDataSchema.parse(pageData());
    const real = lookups({ claims: new Map(), sources: researchSources(), entities: new Map(), criteria: activeCriteria(), valuesPositions: [] });
    assert.deepEqual(matrixEvidenceProblems(data, real), []);
  });
  test('validateMatrixEvidence throws once with every problem listed', () => {
    const data = fixture();
    row(data, 'free-tier').cells.greenpt.sources = ['/research/sources/2026/missing'];
    data.footnotes![0].sources = ['/research/sources/2026/also-missing'];
    assert.throws(() => validateMatrixEvidence(data, lookups()), (e: Error) =>
      e.message.includes('free-tier/greenpt') && e.message.includes('footnotes[0] (A note)'));
    assert.doesNotThrow(() => validateMatrixEvidence(fixture(), lookups()));
  });
});

describe('matrixEvidenceProblems: claims', () => {
  test('a cited claim does not exist', () => {
    expectProblem((d) => { row(d, 'renewable-hosting').cells.greenpt.claim = '/research/claims/greenpt/nope'; },
      'renewable-hosting/greenpt', 'does not exist');
  });
  for (const status of ['draft', 'archived', 'blocked'] as const) {
    test(`a cited claim is ${status}`, () => {
      expectProblem(() => {}, 'renewable-hosting/greenpt', `is ${status}, not published`, withClaim(claim({ status })));
    });
  }
  test('a cited published claim has no reviewer who maps to a person', () => {
    for (const reviewer of [null, 'nobody@example.com']) {
      expectProblem(() => {}, 'renewable-hosting/greenpt', 'no reviewer', withClaim(claim({ reviewer })));
    }
  });
  test('a cell in a row with no criterion cites a claim', () => {
    expectProblem((d) => { row(d, 'free-tier').cells.greenpt.claim = HOSTING; }, 'free-tier/greenpt', 'row has no criterion');
  });
  test("the claim's criteria_slug differs from the row's criterion", () => {
    expectProblem((d) => { row(d, 'renewable-hosting').criterion = 'no-training-on-user-data'; },
      'renewable-hosting/greenpt', 'under criterion "renewable-energy-hosting"');
  });
  test("the claim's entity is neither the product's entity nor its parent company", () => {
    expectProblem(() => {}, 'renewable-hosting/greenpt', 'not GreenPT\'s entity or parent company', withClaim(claim({ entity: 'products/other' })));
  });
  test('a company claim may cite the parent company', () => {
    assert.deepEqual(matrixEvidenceProblems(fixture(), withClaim(claim({ entity: 'companies/greenpt-co' }))), []);
  });
  test('a product with no entity cites a claim', () => {
    const data = fixture();
    delete data.products[0].entity;
    const problems = matrixEvidenceProblems(data, lookups());
    assert.ok(problems.every((p) => p.includes('has no entity')), problems.join('\n'));
    assert.ok(problems.some((p) => p.startsWith('renewable-hosting/greenpt:')), problems.join('\n'));
  });
  test('the verdict disagrees with the answer', () => {
    expectProblem((d) => { row(d, 'renewable-hosting').cells.greenpt.type = 'no'; }, 'renewable-hosting/greenpt', 'does not allow the answer "no"');
  });
  test('inverted polarity: a True verdict allows the answer No and rejects Yes', () => {
    const TRAINING = '/research/claims/greenpt/no-training-on-user-data';
    const l = withClaim(claim({ id: 'greenpt/no-training-on-user-data', criteria_slug: 'no-training-on-user-data' }));
    const data = fixture();
    row(data, 'data-used-for-training').cells.greenpt.claim = TRAINING;
    assert.deepEqual(matrixEvidenceProblems(data, l), []);
    expectProblem((d) => { row(d, 'data-used-for-training').cells.greenpt = { type: 'yes', claim: TRAINING }; },
      'data-used-for-training/greenpt', 'does not allow the answer "yes" (polarity inverted)', l);
  });
  test('an ownership claim must be true or mostly-true', () => {
    expectProblem(() => {}, 'corporate-structure/greenpt', 'only true or mostly-true', withClaim({ ...structureClaim, verdict: 'mixed' }));
  });
  test("an ownership claim's title names a different vocabulary word than the cell's term", () => {
    expectProblem((d) => { row(d, 'corporate-structure').cells.greenpt.term = 'B-corp'; },
      'corporate-structure/greenpt', 'names "privately-held", the cell\'s term is "B-corp"');
  });
  test('a product capped at the Source tier cites a claim', () => {
    const data = fixture();
    row(data, 'renewable-hosting').cells.treadlightly = { type: 'yes', claim: HOSTING };
    const problems = matrixEvidenceProblems(data, lookups());
    assert.ok(problems.some((p) => p.startsWith('renewable-hosting/treadlightly:') && p.includes('capped at the Source tier')), problems.join('\n'));
  });
});

describe('matrixEvidenceProblems: sources', () => {
  const MISSING = '/research/sources/2026/missing';
  const cases: [string, (d: MatrixDataForCheck) => void, string][] = [
    ['a cell', (d) => { row(d, 'free-tier').cells.greenpt.sources = [MISSING]; }, 'free-tier/greenpt'],
    ['a summary entry', (d) => { (d.products[0].summary!.environmental as { sources: string[] }).sources = [MISSING]; }, 'summary.environmental/greenpt'],
    ['a footnote', (d) => { d.footnotes![0].sources = [MISSING]; }, 'footnotes[0] (A note)'],
    ['ideal.sources', (d) => { row(d, 'renewable-hosting').ideal!.sources = [MISSING]; }, 'renewable-hosting: stance'],
    ['large_models.sources', (d) => { (row(d, 'models').ideal as { large_models: { sources: string[] } }).large_models.sources = [MISSING]; }, 'models: large_models'],
    ['owned_by.sources', (d) => { row(d, 'corporate-structure').cells.treadlightly.owned_by!.sources = [MISSING]; }, 'corporate-structure/treadlightly: owned_by'],
  ];
  for (const [name, mutate, where] of cases) {
    test(`a missing source in ${name}`, () => expectProblem(mutate, where, 'does not exist'));
  }
});

describe('matrixEvidenceProblems: rows and cells', () => {
  test('a criterion that does not exist', () => {
    expectProblem((d) => { row(d, 'free-tier').criterion = 'nope'; }, 'free-tier', 'criterion "nope" does not exist');
  });
  test('an ownership cell has no term', () => {
    expectProblem((d) => { delete row(d, 'corporate-structure').cells.treadlightly.term; }, 'corporate-structure/treadlightly', 'no term');
  });
  test("an ownership term outside the criterion's vocabulary", () => {
    expectProblem((d) => { row(d, 'corporate-structure').cells.treadlightly.term = 'charity'; }, 'corporate-structure/treadlightly', 'not in the criterion\'s vocabulary');
  });
  test('terms must split the vocabulary with each word exactly once', () => {
    expectProblem((d) => { (row(d, 'corporate-structure').ideal as { terms: { mixed: string[] } }).terms.mixed = []; },
      'corporate-structure', 'missing: privately-held');
    expectProblem((d) => { (row(d, 'corporate-structure').ideal as { terms: { mixed: string[] } }).terms.mixed = ['privately-held', 'non-profit']; },
      'corporate-structure', 'unknown or repeated: non-profit');
    expectProblem((d) => { (row(d, 'corporate-structure').ideal as { terms: { bad: string[] } }).terms.bad = ['publicly-traded', 'charity']; },
      'corporate-structure', 'unknown or repeated: charity');
  });
  test('an ownership row needs a criterion with a vocabulary', () => {
    expectProblem((d) => { delete row(d, 'corporate-structure').criterion; delete row(d, 'corporate-structure').cells.greenpt.claim; },
      'corporate-structure', 'needs a criterion with a vocabulary');
  });
  test('a models cell lists a model in neither large_models list', () => {
    expectProblem((d) => { row(d, 'models').cells.greenpt.models = ['Mystery 9']; }, 'models/greenpt', 'in neither large_models list');
  });
  test('a name in both large_models lists', () => {
    expectProblem((d) => { (row(d, 'models').ideal as { large_models: { not_large: string[] } }).large_models.not_large.push('Claude Opus'); },
      'models', 'in both large and not_large');
  });
  test('models, term and owned_by outside their rows', () => {
    expectProblem((d) => { row(d, 'free-tier').cells.greenpt.models = ['X']; }, 'free-tier/greenpt', 'models row only');
    expectProblem((d) => { row(d, 'free-tier').cells.greenpt.term = 'non-profit'; }, 'free-tier/greenpt', 'ownership row only');
    expectProblem((d) => { row(d, 'models').cells.greenpt.owned_by = { name: 'O', kind: 'conglomerate' }; }, 'models/greenpt', 'ownership row only');
  });
  test("a cell's answer is not in the row's answers", () => {
    expectProblem((d) => { row(d, 'accessibility').cells.greenpt.type = 'no'; }, 'accessibility/greenpt', 'not one of the row\'s answers');
  });
  test('a row lacks a cell for an active product', () => {
    expectProblem((d) => { delete row(d, 'free-tier').cells.treadlightly; }, 'free-tier/treadlightly', 'no cell for an active product');
  });
  test('a row has a cell for a key that is no product', () => {
    expectProblem((d) => { row(d, 'free-tier').cells.nobody = { type: 'yes' }; }, 'free-tier/nobody', 'no product');
  });
  test('an ideal.position that is not a Values position', () => {
    expectProblem((d) => { row(d, 'renewable-hosting').ideal!.position = '/values#nope'; }, 'renewable-hosting', 'not a Values position');
  });
});

describe('vocabularyWordInTitle', () => {
  test('finds exactly one word, hyphen- and case-insensitively', () => {
    assert.equal(vocabularyWordInTitle('Ecosia has steward-ownership corporate structure', VOCABULARY), 'steward-ownership');
    assert.equal(vocabularyWordInTitle('Infomaniak has a B Corp corporate structure', VOCABULARY), 'B-corp');
    assert.equal(vocabularyWordInTitle('Acme has a corporate structure', VOCABULARY), null);
    assert.equal(vocabularyWordInTitle('Acme is non-profit and cooperative', VOCABULARY), null);
  });
});

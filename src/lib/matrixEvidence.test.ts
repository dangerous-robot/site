import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  cellStance,
  cellTier,
  checkRecordLine,
  citedId,
  popupContent,
  rowKind,
  tierCounts,
  verdictAgrees,
  type Answer,
  type ClaimInfo,
  type EvidenceLookups,
  type Polarity,
  type ProductRef,
  type SourceInfo,
  type Stance,
} from './matrixEvidence';
import type { MatrixCell, MatrixFeature } from './matrixSchema';
import { claim } from './matrixTestFixtures';
import { VERDICT_ORDER, type Verdict } from './verdict';

function source(id: string, over: Partial<SourceInfo> = {}): SourceInfo {
  return {
    id,
    title: `Title of ${id}`,
    publisher: `Publisher of ${id}`,
    accessed_date: new Date('2026-09-30'),
    ...over,
  };
}

function lookups(claims: ClaimInfo[] = [], sources: SourceInfo[] = []): EvidenceLookups {
  return {
    claims: new Map(claims.map((c) => [c.id, c])),
    sources: new Map(sources.map((s) => [s.id, s])),
  };
}

const greenpt: ProductRef = { key: 'greenpt', name: 'GreenPT', status: 'active', entity: 'products/greenpt' };
const treadlightly: ProductRef = { key: 'treadlightly', name: 'TreadLightlyAI', status: 'active', max_tier: 'source' };

const bare: MatrixCell = { type: 'yes' };
const CLAIM_PATH = '/research/claims/greenpt/renewable-energy-hosting';
const SRC_A = '/research/sources/2026/a';
const SRC_B = '/research/sources/2026/b';

function feature(over: Partial<MatrixFeature> = {}): MatrixFeature {
  return { key: 'renewable-hosting', label: 'Hosted on renewable energy', group: 'environmental', polarity: 'same', cells: {}, ...over };
}

describe('citedId', () => {
  test('strips the rendered prefix', () => {
    assert.equal(citedId(CLAIM_PATH, 'claim'), 'greenpt/renewable-energy-hosting');
    assert.equal(citedId('/research/sources/2026/a/', 'source'), '2026/a');
  });
  test('rejects the wrong prefix or an empty id', () => {
    assert.equal(citedId(CLAIM_PATH, 'source'), null);
    assert.equal(citedId('/research/claims/', 'claim'), null);
    assert.equal(citedId('https://example.com', 'source'), null);
  });
});

describe('verdictAgrees', () => {
  const ANSWERS: Answer[] = ['yes', 'no', 'partial', 'unknown', 'na'];
  // The plan's table, both columns written out, so the test does not derive one from the other.
  const TABLE: Record<Verdict, { same: Answer[]; inverted: Answer[] }> = {
    'true': { same: ['yes'], inverted: ['no'] },
    'mostly-true': { same: ['yes', 'partial'], inverted: ['no', 'partial'] },
    'mixed': { same: ['partial'], inverted: ['partial'] },
    'mostly-false': { same: ['no', 'partial'], inverted: ['yes', 'partial'] },
    'false': { same: ['no'], inverted: ['yes'] },
    'unverified': { same: ['unknown'], inverted: ['unknown'] },
    'not-applicable': { same: ['na'], inverted: ['na'] },
  };

  for (const verdict of VERDICT_ORDER) {
    for (const polarity of ['same', 'inverted'] as Polarity[]) {
      for (const answer of ANSWERS) {
        const expected = TABLE[verdict][polarity].includes(answer);
        test(`${verdict} x ${answer} (${polarity}) is ${expected}`, () => {
          assert.equal(verdictAgrees(verdict, answer, polarity), expected);
        });
      }
    }
  }
  test('polarity defaults to same', () => {
    assert.equal(verdictAgrees('true', 'yes'), true);
    assert.equal(verdictAgrees('true', 'no'), false);
  });
  test('text answers never agree with a verdict', () => {
    assert.equal(verdictAgrees('true', 'text'), false);
  });
});

describe('rowKind', () => {
  test('tells the four row kinds apart by the ideal', () => {
    assert.equal(rowKind({}), 'feature');
    assert.equal(rowKind({ ideal: { value: 'yes' } }), 'yes-no');
    assert.equal(rowKind({ ideal: { answer: 'x', large_models: { large: [], not_large: [] } } }), 'models');
    assert.equal(rowKind({ ideal: { answer: 'x', terms: { good: [], mixed: [], bad: [] } } }), 'ownership');
  });
});

describe('cellStance: yes/no rows', () => {
  const cases: ['yes' | 'no', Answer, Stance][] = [
    ['yes', 'yes', 'good'],
    ['yes', 'no', 'bad'],
    ['yes', 'partial', 'mixed'],
    ['yes', 'unknown', 'neutral'],
    ['yes', 'na', 'neutral'],
    ['no', 'no', 'good'],
    ['no', 'yes', 'bad'],
    ['no', 'partial', 'mixed'],
    ['no', 'unknown', 'neutral'],
    ['no', 'na', 'neutral'],
  ];
  for (const [ideal, answer, expected] of cases) {
    test(`stance ${ideal}, answer ${answer} is ${expected}`, () => {
      assert.equal(cellStance({ type: answer }, feature({ ideal: { value: ideal } })), expected);
    });
  }
  test('a feature row (no ideal) is neutral for every answer', () => {
    for (const answer of ['yes', 'no', 'partial', 'unknown', 'na', 'text'] as Answer[]) {
      assert.equal(cellStance({ type: answer }, feature()), 'neutral');
    }
  });
});

describe('cellStance: models row', () => {
  const models = feature({
    key: 'models',
    label: 'Models',
    ideal: {
      answer: 'no large models',
      large_models: { large: ['Claude Opus', 'Gemini Pro'], not_large: ['Claude Sonnet', 'Gemini Flash'] },
    },
  });
  test('no models listed is unknown (neutral)', () => {
    assert.equal(cellStance({ type: 'text', detail: 'GPT' }, models), 'neutral');
    assert.equal(cellStance({ type: 'text', models: [] }, models), 'neutral');
  });
  test('none large is good', () => {
    assert.equal(cellStance({ type: 'text', models: ['Claude Sonnet', 'Gemini Flash'] }, models), 'good');
  });
  test('all large is bad', () => {
    assert.equal(cellStance({ type: 'text', models: ['Claude Opus', 'Gemini Pro'] }, models), 'bad');
  });
  test('some large is bad (R1: no mixed on this row)', () => {
    assert.equal(cellStance({ type: 'text', models: ['Claude Sonnet', 'Gemini Pro'] }, models), 'bad');
  });
  test('a model in neither list is neutral (the build check reports it)', () => {
    assert.equal(cellStance({ type: 'text', models: ['Claude Sonnet', 'Mystery 9'] }, models), 'neutral');
  });
});

describe('cellStance: ownership row', () => {
  const ownership = feature({
    key: 'corporate-structure',
    label: 'Ownership structure',
    ideal: {
      answer: 'non-profit or similar',
      terms: {
        good: ['non-profit', 'steward-ownership', 'cooperative', 'B-corp', 'employee-owned'],
        mixed: ['privately-held'],
        bad: ['publicly-traded'],
      },
    },
  });
  for (const term of ['non-profit', 'steward-ownership', 'cooperative', 'B-corp', 'employee-owned']) {
    test(`${term} is good`, () => {
      assert.equal(cellStance({ type: 'text', term }, ownership), 'good');
    });
  }
  test('privately-held is mixed', () => {
    assert.equal(cellStance({ type: 'text', term: 'privately-held' }, ownership), 'mixed');
  });
  test('publicly-traded is bad', () => {
    assert.equal(cellStance({ type: 'text', term: 'publicly-traded' }, ownership), 'bad');
  });
  test('an owner makes a good term bad (P6)', () => {
    const cell = { type: 'text' as Answer, term: 'B-corp', owned_by: { name: 'Big Co', kind: 'publicly-traded' as const } };
    assert.equal(cellStance(cell, ownership), 'bad');
  });
  test('no term is neutral', () => {
    assert.equal(cellStance({ type: 'text', detail: 'Private' }, ownership), 'neutral');
  });
});

describe('cellTier', () => {
  test('nothing cited is "none"', () => {
    assert.equal(cellTier(bare, greenpt, lookups()), 'none');
    assert.equal(cellTier({ type: 'yes', last_checked: '2026-10-01' }, greenpt, lookups()), 'none');
  });
  test('sources only is "source"', () => {
    assert.equal(cellTier({ type: 'yes', sources: [SRC_A] }, greenpt, lookups([], [source('2026/a')])), 'source');
  });
  test('a published claim with a named reviewer is "claim"', () => {
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH }, greenpt, lookups([claim()])), 'claim');
  });
  test('a published claim with reviewed_at but reviewer null is not "claim"', () => {
    const l = lookups([claim({ reviewer: null })]);
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH }, greenpt, l), 'none');
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH, sources: [SRC_A] }, greenpt, l), 'source');
  });
  test('a draft or archived claim is not "claim"', () => {
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH }, greenpt, lookups([claim({ status: 'draft' })])), 'none');
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH }, greenpt, lookups([claim({ status: 'archived' })])), 'none');
  });
  test('a reviewer with no entry in reviewers.ts is not "claim"', () => {
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH }, greenpt, lookups([claim({ reviewer: 'nobody@example.com' })])), 'none');
  });
  test('a missing claim is not "claim"', () => {
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH }, greenpt, lookups()), 'none');
  });
  test('TreadLightlyAI is capped at "source" even with a reviewed claim', () => {
    const l = lookups([claim()]);
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH }, treadlightly, l), 'none');
    assert.equal(cellTier({ type: 'yes', claim: CLAIM_PATH, sources: [SRC_A] }, treadlightly, l), 'source');
  });
  test('an ownership cell with an owner takes the lower of the two tiers', () => {
    const l = lookups([claim()], [source('2026/a')]);
    const owner = { name: 'Big Co', kind: 'publicly-traded' as const };
    assert.equal(cellTier({ type: 'text', term: 'B-corp', claim: CLAIM_PATH, owned_by: owner }, greenpt, l), 'none');
    assert.equal(cellTier({ type: 'text', term: 'B-corp', claim: CLAIM_PATH, owned_by: { ...owner, sources: [SRC_A] } }, greenpt, l), 'source');
    assert.equal(cellTier({ type: 'text', term: 'B-corp', sources: [SRC_A], owned_by: { ...owner, sources: [SRC_A] } }, greenpt, l), 'source');
    assert.equal(cellTier({ type: 'text', term: 'B-corp', owned_by: { ...owner, sources: [SRC_A] } }, greenpt, l), 'none');
  });
});

describe('popupContent', () => {
  const row = feature();
  test('reviewed claim: verdict, confidence, as-of date and a claim-page link', () => {
    const c = popupContent({ type: 'yes', claim: CLAIM_PATH }, greenpt, row, lookups([claim()]));
    assert.equal(c.tier, 'claim');
    assert.equal(c.tierName, 'Reviewed claim');
    assert.equal(c.verdict, 'true');
    assert.equal(c.confidence, 'High');
    assert.equal(c.asOf, '2026-09-28');
    assert.deepEqual(c.link, { href: CLAIM_PATH, text: 'Open claim page', srText: 'for GreenPT, hosted on renewable energy' });
  });
  test('one source: publisher and accessed date, link to the Evidence entry', () => {
    const c = popupContent({ type: 'no', sources: [SRC_A] }, greenpt, row, lookups([], [source('2026/a')]));
    assert.equal(c.tier, 'source');
    assert.equal(c.sourceLine, 'Publisher of 2026/a, accessed 2026-09-30');
    assert.deepEqual(c.link, { href: '#ev-renewable-hosting-greenpt', text: 'See sources below', srText: 'for GreenPT, hosted on renewable energy' });
  });
  test('several sources: "and N more", counting owner sources too', () => {
    const l = lookups([], [source('2026/a'), source('2026/b')]);
    const c = popupContent({ type: 'no', sources: [SRC_A, SRC_B] }, greenpt, row, l);
    assert.equal(c.sourceLine, 'Publisher of 2026/a, accessed 2026-09-30, and 1 more');
    const owner = { name: 'Big Co', kind: 'publicly-traded' as const, sources: [SRC_B] };
    const o = popupContent({ type: 'text', term: 'B-corp', sources: [SRC_A], owned_by: owner }, greenpt, row, l);
    assert.equal(o.sourceLine, 'Publisher of 2026/a, accessed 2026-09-30, and 1 more');
  });
  test('capped product with a claim and sources shows the source tier', () => {
    const c = popupContent({ type: 'yes', claim: CLAIM_PATH, sources: [SRC_A] }, treadlightly, row, lookups([claim()], [source('2026/a')]));
    assert.equal(c.tier, 'source');
    assert.equal(c.verdict, undefined);
  });
  test('a summary column is a subject too: the link lands on ev-summary-<field>-<product>', () => {
    const subject = { key: 'summary-environmental', label: 'Environmental summary' };
    const c = popupContent({ sources: [SRC_A] }, greenpt, subject, lookups([], [source('2026/a')]));
    assert.equal(c.link?.href, '#ev-summary-environmental-greenpt');
    assert.equal(c.link?.srText, 'for GreenPT, environmental summary');
  });
  test('not yet sourced: tier none and no link', () => {
    const none = popupContent(bare, greenpt, row, lookups());
    assert.equal(none.tier, 'none');
    assert.equal(none.tierName, 'Not yet sourced');
    assert.equal(none.link, undefined);
  });
});

describe('checkRecordLine', () => {
  test('names the check date when there is one', () => {
    assert.equal(checkRecordLine({}), 'Not yet sourced.');
    assert.equal(checkRecordLine({ last_checked: '2026-10-12' }), 'Checked by Dangerous Robot, 2026-10-12. Not yet sourced.');
  });
});

describe('tierCounts', () => {
  test('counts every active product cell by tier', () => {
    const excluded: ProductRef = { key: 'gone', name: 'Gone', status: 'excluded' };
    const data = {
      products: [greenpt, treadlightly, excluded],
      features: [
        feature({ cells: { greenpt: { type: 'yes', claim: CLAIM_PATH }, treadlightly: { type: 'yes', sources: [SRC_A] }, gone: { type: 'yes', sources: [SRC_A] } } }),
        feature({ key: 'free-tier', label: 'Free tier', cells: { greenpt: { type: 'yes' } } }),
      ],
    };
    assert.deepEqual(tierCounts(data, lookups([claim()], [source('2026/a')])), { claim: 1, source: 1, none: 1 });
  });
});

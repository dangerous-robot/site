import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { matrixEvidenceProblems, type CheckLookups, type MatrixDataForCheck } from './matrixCheck';
import { VALUES_POSITIONS, VALUES_POSITION_IDS, positionHeading } from './valuesPositions';

describe('VALUES_POSITIONS', () => {
  test('lists the five position headings of the Values page, each id the slug of its heading', () => {
    assert.deepEqual(VALUES_POSITIONS.map((p) => p.id), [
      'ai-safety-is-unsolved',
      'ai-is-fueling-environmental-destruction',
      'ai-outcomes-are-being-decided-by-a-small-group-of-people',
      'people-have-a-right-to-informed-choices-about-ai',
      'staying-human-and-connected-to-each-other-will-be-essential',
    ]);
    assert.deepEqual(VALUES_POSITION_IDS, VALUES_POSITIONS.map((p) => p.id));
  });

  test('positionHeading names the heading behind a /values# link, or nothing for an unknown one', () => {
    assert.equal(positionHeading('/values#ai-is-fueling-environmental-destruction'), 'AI is fueling environmental destruction');
    assert.equal(positionHeading('/values#our-contradictions'), undefined);
  });
});

describe('the build check reads the same list', () => {
  const lookups: CheckLookups = {
    claims: new Map(),
    sources: new Map(),
    entities: new Map(),
    criteria: new Map(),
    valuesPositions: VALUES_POSITION_IDS,
  };
  const data = (position: string): MatrixDataForCheck => ({
    products: [{ key: 'p', name: 'P', status: 'active' }],
    features: [{
      key: 'row', label: 'Row', group: 'environmental', polarity: 'same',
      ideal: { value: 'yes', position },
      cells: { p: { type: 'yes' } },
    }],
  });

  test('every listed position passes', () => {
    for (const id of VALUES_POSITION_IDS) {
      assert.deepEqual(matrixEvidenceProblems(data(`/values#${id}`), lookups), []);
    }
  });

  test('a Values heading that is not a position fails, naming the row', () => {
    const problems = matrixEvidenceProblems(data('/values#our-contradictions'), lookups);
    assert.equal(problems.length, 1);
    assert.match(problems[0], /^row: stance position "\/values#our-contradictions" is not a Values position$/);
  });
});

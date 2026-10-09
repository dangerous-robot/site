import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import yaml from 'js-yaml';
import { matrixDataSchema, matrixCell, matrixFeature, summaryText } from './matrixSchema';
import { pageData } from './matrixTestFixtures';
import { collectFreshestDate } from './resourceSchema';

function issues(result: { success: boolean; error?: { issues: { message: string }[] } }): string {
  return result.success ? '' : result.error!.issues.map((i) => i.message).join('\n');
}

describe('matrixDataSchema', () => {
  test('accepts the page data as migrated', () => {
    const result = matrixDataSchema.safeParse(pageData());
    assert.ok(result.success, issues(result));
  });

  test('rejects the retired cell types', () => {
    assert.equal(matrixCell.safeParse({ type: 'no-good' }).success, false);
    assert.equal(matrixCell.safeParse({ type: 'planned' }).success, false);
  });

  test('rejects the removed cell footnote field and any other unknown key', () => {
    assert.equal(matrixCell.safeParse({ type: 'yes', footnote: 'x' }).success, false);
    assert.equal(matrixCell.safeParse({ type: 'yes', source: ['/research/sources/2026/a'] }).success, false);
  });

  const row = { key: 'r', label: 'Row', group: 'business', cells: {} };

  test('rejects an unknown polarity', () => {
    assert.equal(matrixFeature.safeParse({ ...row, polarity: 'flipped' }).success, false);
    assert.equal(matrixFeature.safeParse({ ...row, polarity: 'inverted' }).success, true);
    assert.equal(matrixFeature.parse(row).polarity, 'same');
  });

  test('ideal is one of three shapes: value, answer + large_models, answer + terms', () => {
    const lists = { large: ['A'], not_large: ['B'] };
    const terms = { good: ['non-profit'], mixed: ['privately-held'], bad: ['publicly-traded'] };
    assert.equal(matrixFeature.safeParse({ ...row, ideal: { value: 'yes', answer: 'x' } }).success, false);
    assert.equal(matrixFeature.safeParse({ ...row, ideal: { note: 'no value or answer' } }).success, false);
    assert.equal(matrixFeature.safeParse({ ...row, ideal: { answer: 'bare answer' } }).success, false);
    assert.equal(matrixFeature.safeParse({ ...row, ideal: { value: 'yes', large_models: lists } }).success, false);
    assert.equal(matrixFeature.safeParse({ ...row, ideal: { value: 'yes' } }).success, true);
    assert.equal(matrixFeature.safeParse({ ...row, ideal: { answer: 'no large models', large_models: lists } }).success, true);
    assert.equal(matrixFeature.safeParse({ ...row, ideal: { answer: 'non-profit or similar', terms } }).success, true);
  });

  test('ideal.value is yes or no', () => {
    assert.equal(matrixFeature.safeParse({ ...row, ideal: { value: 'partial' } }).success, false);
  });

  test('rejects an unknown owned_by.kind', () => {
    const cell = { type: 'text', term: 'B-corp', owned_by: { name: 'Big Co', kind: 'charity' } };
    assert.equal(matrixCell.safeParse(cell).success, false);
    assert.equal(matrixCell.safeParse({ ...cell, owned_by: { name: 'Big Co', kind: 'conglomerate' } }).success, true);
  });

  test('citations must be rendered paths', () => {
    assert.equal(matrixCell.safeParse({ type: 'yes', sources: ['2026/a'] }).success, false);
    assert.equal(matrixCell.safeParse({ type: 'yes', sources: ['/research/sources/2026/a'] }).success, true);
    assert.equal(matrixCell.safeParse({ type: 'yes', claim: 'https://example.com' }).success, false);
    assert.equal(matrixCell.safeParse({ type: 'yes', claim: '/research/claims/greenpt/renewable-energy-hosting' }).success, true);
  });

  test('last_checked accepts a quoted day or an unquoted YAML date, and stores the day', () => {
    assert.equal(matrixCell.parse({ type: 'yes', last_checked: '2026-10-12' }).last_checked, '2026-10-12');
    const unquoted = yaml.load('type: yes\nlast_checked: 2026-10-12') as object;
    assert.equal(matrixCell.parse(unquoted).last_checked, '2026-10-12');
    assert.equal(matrixCell.safeParse({ type: 'yes', last_checked: 'October 12' }).success, false);
  });

  test('a summary entry may be a string or an object with text and sources', () => {
    const data = pageData() as { products: { summary: Record<string, unknown> }[] };
    data.products[0].summary.environmental = {
      text: 'Hosted at Scaleway.',
      sources: ['/research/sources/2026/example'],
      last_checked: '2026-10-12',
    };
    const result = matrixDataSchema.safeParse(data);
    assert.ok(result.success, issues(result));
    assert.equal(summaryText(result.data!.products[0].summary!.environmental), 'Hosted at Scaleway.');
    data.products[0].summary.environmental = { text: '   ' };
    assert.equal(matrixDataSchema.safeParse(data).success, false);
  });
});

describe('collectFreshestDate', () => {
  test('counts an unquoted YAML date (a Date object) as well as a quoted one', () => {
    const unquoted = yaml.load('cells:\n  a:\n    last_checked: 2026-10-12\n');
    assert.equal(collectFreshestDate(unquoted), '2026-10-12T00:00:00.000Z');
    const quoted = yaml.load('cells:\n  a:\n    last_checked: "2026-10-12"\n');
    assert.equal(collectFreshestDate(quoted), '2026-10-12T00:00:00.000Z');
  });
  test('takes the freshest of several and ignores other keys', () => {
    const v = { a: { last_checked: '2026-01-01' }, b: [{ last_verified: '2026-03-01' }], c: { as_of: '2027-01-01' } };
    assert.equal(collectFreshestDate(v), '2026-03-01T00:00:00.000Z');
    assert.equal(collectFreshestDate({ a: 1 }), undefined);
  });
});

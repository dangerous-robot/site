import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { isAlphaDetailPath, shouldIncludeInSitemap, shouldNoindex } from './seo';

const CLAIM_PAGES = [
  '/research/claims/acme/some-claim',
  '/research/claims/acme/some-claim/',
  '/research/claims/subjects/ai-safety/some-claim',
  '/research/claims/subjects/ai-safety/some-claim/',
  '/research/claims/acme/nested/some-claim',
  '/research/claims/acme/nested/some-claim/',
  '/research/claims/subjects/ai-safety/nested/some-claim',
  '/research/claims/subjects/ai-safety/nested/some-claim/',
];

const LIST_PAGES = [
  '/research/claims',
  '/research/claims/',
  '/research/claims/subjects',
  '/research/claims/subjects/',
  '/research/claims/subjects/ai-safety',
  '/research/claims/subjects/ai-safety/',
];

describe('isAlphaDetailPath for claims', () => {
  for (const path of CLAIM_PAGES) {
    test(`matches claim page ${path}`, () => {
      assert.equal(isAlphaDetailPath(path), true);
    });
  }
  for (const path of LIST_PAGES) {
    test(`does not match list page ${path}`, () => {
      assert.equal(isAlphaDetailPath(path), false);
    });
  }
});

describe('subject claim pages are noindexed and left out of the sitemap', () => {
  const path = '/research/claims/subjects/ai-safety/some-claim';
  test('shouldNoindex is true', () => {
    assert.equal(shouldNoindex(path), true);
  });
  test('shouldIncludeInSitemap is false', () => {
    assert.equal(shouldIncludeInSitemap(path), false);
  });
});

describe('the claims list page stays indexable', () => {
  test('shouldNoindex is false and the sitemap keeps it', () => {
    assert.equal(shouldNoindex('/research/claims/'), false);
    assert.equal(shouldIncludeInSitemap('/research/claims/'), true);
  });
});

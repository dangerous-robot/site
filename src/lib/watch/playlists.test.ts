import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import yaml from 'js-yaml';
import { curatedFileSchema } from './schema';

function parse(relativeToHere: string) {
  const text = readFileSync(new URL(relativeToHere, import.meta.url), 'utf8');
  return curatedFileSchema.safeParse(yaml.load(text));
}

function pairs(result: ReturnType<typeof parse>) {
  return [...(result.data?.playlists ?? [])]
    .sort((a, b) => a.order - b.order)
    .map((p) => [p.slug, p.playlist_id]);
}

describe('curated playlist files', () => {
  test('src/content/watch/playlists.yaml validates and keeps the seed order', () => {
    const result = parse('../../content/watch/playlists.yaml');
    assert.equal(result.success, true, result.error?.message);
    assert.deepEqual(pairs(result), [
      ['dangerous-robot', 'PLXFc9I7KsRUk'],
      ['far-ai-research-highlights', 'PLpvkFqYJXcreU5HqW6aUYeppYPG8aBRZ_'],
      ['oxford-ethics-colloquia', 'PLf4lTwFHevBuvTDX4m8N5WVAX62IkhXJ7'],
    ]);
  });

  // Fixture API responses, the dist check and browser tests key off these pairs.
  test('fixtures/playlists.fixture.yaml validates with the four fixture playlists', () => {
    const result = parse('./fixtures/playlists.fixture.yaml');
    assert.equal(result.success, true, result.error?.message);
    assert.deepEqual(pairs(result), [
      ['alpha', 'PLfixtureAlpha01'],
      ['bravo', 'PLfixtureBravo02'],
      ['charlie', 'PLfixtureCharlie3'],
      ['delta', 'PLfixtureDelta04'],
    ]);
  });
});

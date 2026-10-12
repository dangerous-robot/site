import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { createFixtureFetch, fixtureFetch } from './fixtureFetch';
import { API_BASE } from './youtube';
import playlistsBody from './fixtures/api/playlists.json';
import alphaPage1 from './fixtures/api/playlistItems-alpha-1.json';
import alphaPage2 from './fixtures/api/playlistItems-alpha-2.json';
import bravoItems from './fixtures/api/playlistItems-bravo.json';
import videosBody from './fixtures/api/videos.json';
import { VIDEO_ID_RE } from './schema';

async function get(path: string, params: Record<string, string>, fetch = fixtureFetch) {
  const res = await fetch(`${API_BASE}/${path}?${new URLSearchParams(params)}`, { signal: AbortSignal.timeout(1000) });
  return { status: res.status, body: JSON.parse(await res.text()) };
}

describe('fixtureFetch', () => {
  test('playlists.list returns only the requested IDs, and never Delta', async () => {
    const { status, body } = await get('playlists', { id: 'PLfixtureBravo02,PLfixtureDelta04' });
    assert.equal(status, 200);
    assert.deepEqual(body.items.map((p: { id: string }) => p.id), ['PLfixtureBravo02']);
  });

  test('Alpha has two pages linked by nextPageToken', async () => {
    const first = await get('playlistItems', { playlistId: 'PLfixtureAlpha01' });
    assert.ok(first.body.nextPageToken);
    const second = await get('playlistItems', { playlistId: 'PLfixtureAlpha01', pageToken: first.body.nextPageToken });
    assert.equal(second.status, 200);
    assert.equal(second.body.nextPageToken, undefined);
  });

  test('Charlie playlistItems is a 404 playlistNotFound', async () => {
    const { status, body } = await get('playlistItems', { playlistId: 'PLfixtureCharlie3' });
    assert.equal(status, 404);
    assert.equal(body.error.errors[0].reason, 'playlistNotFound');
  });

  test('videos.list leaves out IDs it does not have, like a deleted video', async () => {
    const { body } = await get('videos', { id: 'fxAlpha0001,fxAlphaDel1' });
    assert.deepEqual(body.items.map((v: { id: string }) => v.id), ['fxAlpha0001']);
  });

  test('a global error mode answers every request with that error', async () => {
    const cases = [['quota', 403, 'quotaExceeded'], ['referer', 403, 'forbidden'], ['key-invalid', 400, 'keyInvalid']] as const;
    for (const [mode, status, reason] of cases) {
      const res = await get('playlists', { id: 'PLfixtureAlpha01' }, createFixtureFetch({ globalError: mode }));
      assert.equal(res.status, status, mode);
      assert.equal(res.body.error.errors[0].reason, reason, mode);
    }
  });

  test('fixture IDs are synthetic and video IDs are exactly 11 characters', () => {
    for (const p of playlistsBody.items) assert.match(p.id, /^PLfixture/);
    const itemIds = [...alphaPage1.items, ...alphaPage2.items, ...bravoItems.items].map((i) => i.snippet.resourceId.videoId);
    for (const id of [...itemIds, ...videosBody.items.map((v) => v.id)]) {
      assert.match(id, VIDEO_ID_RE, id);
      assert.match(id, /^fx/, id);
    }
  });
});

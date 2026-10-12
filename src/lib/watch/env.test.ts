import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { createWatchClient, missingKeyWarning, resolveMode } from './env';
import { reply } from './fixtureFetch';
import type { FetchLike } from './youtube';

const KEY = 'zzTestKeyMarker-7Q2';

describe('resolveMode (U15)', () => {
  test('no key and no fixture flag is none', () => {
    assert.deepEqual(resolveMode({}), { mode: 'none', key: null, expectKey: false, githubActions: false });
  });

  test('an empty or blank key is no key', () => {
    for (const value of ['', '   ']) {
      const env = resolveMode({ YOUTUBE_API_KEY: value });
      assert.equal(env.mode, 'none', JSON.stringify(value));
      assert.equal(env.key, null);
    }
  });

  test('a key gives live mode and carries the key', () => {
    const env = resolveMode({ YOUTUBE_API_KEY: KEY });
    assert.equal(env.mode, 'live');
    assert.equal(env.key, KEY);
  });

  test('WATCH_DATA=fixture wins over a present key, and drops the key', () => {
    const env = resolveMode({ WATCH_DATA: 'fixture', YOUTUBE_API_KEY: KEY });
    assert.equal(env.mode, 'fixture');
    assert.equal(env.key, null);
  });

  test('other WATCH_DATA values are ignored', () => {
    assert.equal(resolveMode({ WATCH_DATA: 'live' }).mode, 'none');
    assert.equal(resolveMode({ WATCH_DATA: 'Fixture', YOUTUBE_API_KEY: KEY }).mode, 'live');
  });

  test('WATCH_EXPECT_KEY and GITHUB_ACTIONS flags', () => {
    const env = resolveMode({ WATCH_EXPECT_KEY: '1', GITHUB_ACTIONS: 'true' });
    assert.equal(env.expectKey, true);
    assert.equal(env.githubActions, true);
    assert.equal(resolveMode({ WATCH_EXPECT_KEY: 'yes', GITHUB_ACTIONS: '1' }).expectKey, false);
    assert.equal(resolveMode({ GITHUB_ACTIONS: '1' }).githubActions, false);
  });
});

describe('missingKeyWarning (U15)', () => {
  test('warns only in none mode when a key is expected', () => {
    assert.match(missingKeyWarning(resolveMode({ WATCH_EXPECT_KEY: '1' })) ?? '', /YOUTUBE_API_KEY is not set/);
    assert.match(missingKeyWarning(resolveMode({ WATCH_EXPECT_KEY: '1', YOUTUBE_API_KEY: '' })) ?? '', /not set/);
    assert.equal(missingKeyWarning(resolveMode({})), null);
    assert.equal(missingKeyWarning(resolveMode({ WATCH_EXPECT_KEY: '1', YOUTUBE_API_KEY: KEY })), null);
    assert.equal(missingKeyWarning(resolveMode({ WATCH_EXPECT_KEY: '1', WATCH_DATA: 'fixture' })), null);
  });
});

describe('createWatchClient', () => {
  function recordingFetch() {
    const urls: string[] = [];
    const fetch: FetchLike = async (url) => {
      urls.push(url);
      return reply(200, { items: [] });
    };
    return { fetch, urls };
  }

  test('none mode has no client', async () => {
    assert.equal(await createWatchClient(resolveMode({})), null);
  });

  test('fixture mode answers from fixtures and never calls the live fetch', async () => {
    const live = recordingFetch();
    const client = await createWatchClient(resolveMode({ WATCH_DATA: 'fixture', YOUTUBE_API_KEY: KEY }), live.fetch);
    const playlists = await client!.listPlaylists(['PLfixtureAlpha01']);
    assert.equal(playlists[0].id, 'PLfixtureAlpha01');
    assert.deepEqual(live.urls, []);
  });

  test('live mode calls the given fetch with the key', async () => {
    const live = recordingFetch();
    const client = await createWatchClient(resolveMode({ YOUTUBE_API_KEY: KEY }), live.fetch);
    await client!.listPlaylists(['PLfixtureAlpha01']);
    assert.equal(new URL(live.urls[0]).searchParams.get('key'), KEY);
  });
});

import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { curatedFileSchema, watchPlaylistSchema, MAX_VIDEOS_DEFAULT } from './schema';
import type { WatchPlaylist, WatchVideo } from './types';

const entry = (overrides: Record<string, unknown> = {}) => ({
  slug: 'alpha',
  playlist_id: 'PLfixtureAlpha01',
  order: 1,
  description: 'An editor description.',
  ...overrides,
});

const second = (overrides: Record<string, unknown> = {}) => entry({
  slug: 'bravo',
  playlist_id: 'PLfixtureBravo02',
  order: 2,
  ...overrides,
});

function messages(result: { success: boolean; error?: { issues: { message: string }[] } }): string {
  return (result.error?.issues ?? []).map((i) => i.message).join(' | ');
}

describe('curatedFileSchema (U7)', () => {
  test('control: a valid list parses and max_videos defaults', () => {
    const result = curatedFileSchema.safeParse({ playlists: [entry(), second({ max_videos: 10, creator: 'Someone' })] });
    assert.equal(result.success, true, messages(result));
    assert.equal(result.data?.playlists[0].max_videos, MAX_VIDEOS_DEFAULT);
    assert.equal(result.data?.playlists[1].max_videos, 10);
  });

  test('control: description is optional', () => {
    const { description: _omit, ...noDescription } = entry();
    assert.equal(curatedFileSchema.safeParse({ playlists: [noDescription] }).success, true);
  });

  test('rejects a duplicate slug', () => {
    const result = curatedFileSchema.safeParse({ playlists: [entry(), second({ slug: 'alpha' })] });
    assert.equal(result.success, false);
    assert.match(messages(result), /slug "alpha" is already used/);
  });

  test('rejects a duplicate playlist_id', () => {
    const result = curatedFileSchema.safeParse({ playlists: [entry(), second({ playlist_id: 'PLfixtureAlpha01' })] });
    assert.equal(result.success, false);
    assert.match(messages(result), /playlist_id "PLfixtureAlpha01" is already used/);
  });

  test('rejects a duplicate order', () => {
    const result = curatedFileSchema.safeParse({ playlists: [entry(), second({ order: 1 })] });
    assert.equal(result.success, false);
    assert.match(messages(result), /order 1 is already used/);
  });

  test('rejects a slug that is not kebab-case', () => {
    for (const slug of ['Alpha', 'alpha_beta', 'alpha--beta', '-alpha', 'alpha-', 'al pha', '']) {
      assert.equal(curatedFileSchema.safeParse({ playlists: [entry({ slug })] }).success, false, slug);
    }
  });

  test('rejects a bad playlist ID shape', () => {
    for (const playlist_id of ['XFc9I7KsRUk', 'PLshort', 'PL' + 'a'.repeat(33), 'PLfixture Alpha', 'UUfixtureAlpha01']) {
      assert.equal(curatedFileSchema.safeParse({ playlists: [entry({ playlist_id })] }).success, false, playlist_id);
    }
  });

  test('control: the seed playlist ID shapes pass', () => {
    for (const playlist_id of ['PLXFc9I7KsRUk', 'PLpvkFqYJXcreU5HqW6aUYeppYPG8aBRZ_', 'PLf4lTwFHevBuvTDX4m8N5WVAX62IkhXJ7']) {
      assert.equal(curatedFileSchema.safeParse({ playlists: [entry({ playlist_id })] }).success, true, playlist_id);
    }
  });

  test('rejects a description over 200 characters', () => {
    assert.equal(curatedFileSchema.safeParse({ playlists: [entry({ description: 'x'.repeat(200) })] }).success, true);
    assert.equal(curatedFileSchema.safeParse({ playlists: [entry({ description: 'x'.repeat(201) })] }).success, false);
  });

  test('rejects an unknown key on an entry and at the top level', () => {
    assert.equal(curatedFileSchema.safeParse({ playlists: [entry({ title: 'stray' })] }).success, false);
    assert.equal(curatedFileSchema.safeParse({ playlists: [entry()], extra: true }).success, false);
  });

  test('rejects a bad order or max_videos', () => {
    for (const bad of [{ order: 0 }, { order: 1.5 }, { max_videos: 0 }, { max_videos: 201 }]) {
      assert.equal(curatedFileSchema.safeParse({ playlists: [entry(bad)] }).success, false, JSON.stringify(bad));
    }
  });

  test('rejects an empty list', () => {
    assert.equal(curatedFileSchema.safeParse({ playlists: [] }).success, false);
  });
});

const video = (overrides: Partial<WatchVideo> = {}): WatchVideo => ({
  id: 'fxAlpha0001',
  title: 'Fixture video',
  channel: 'Fixture channel',
  durationText: '22:58',
  durationSpoken: '22 minutes 58 seconds',
  publishedIso: '2025-11-03T17:00:00Z',
  description: 'A plain-text description.',
  cover: {
    src: 'https://i.ytimg.com/vi/fxAlpha0001/hqdefault.jpg',
    srcset: 'https://i.ytimg.com/vi/fxAlpha0001/mqdefault.jpg 320w, https://i.ytimg.com/vi/fxAlpha0001/hqdefault.jpg 480w',
  },
  frameTier: 'mq',
  ...overrides,
});

const playlist = (overrides: Partial<WatchPlaylist> = {}): WatchPlaylist => ({
  slug: 'alpha',
  youtubeId: 'PLfixtureAlpha01',
  order: 1,
  name: 'Alpha',
  creator: 'Fixture channel',
  description: 'An editor description.',
  status: 'ok',
  dataMode: 'fixture',
  videos: [video(), video({ id: 'fxAlpha0002', frameTier: 'sd', durationText: '', durationSpoken: '' })],
  ...overrides,
});

describe('watchPlaylistSchema (U7)', () => {
  test('accepts normalized output', () => {
    const result = watchPlaylistSchema.safeParse(playlist());
    assert.equal(result.success, true, messages(result));
  });

  test('accepts empty and failed playlists with no videos and no creator', () => {
    for (const status of ['empty', 'failed'] as const) {
      const { creator: _omit, ...noCreator } = playlist({ status, videos: [] });
      assert.equal(watchPlaylistSchema.safeParse(noCreator).success, true, status);
    }
  });

  test('rejects a status that disagrees with the video list', () => {
    assert.equal(watchPlaylistSchema.safeParse(playlist({ status: 'ok', videos: [] })).success, false);
    assert.equal(watchPlaylistSchema.safeParse(playlist({ status: 'empty' })).success, false);
    assert.equal(watchPlaylistSchema.safeParse(playlist({ status: 'failed' })).success, false);
  });

  test('description limits allow one ellipsis character past the cut', () => {
    assert.equal(watchPlaylistSchema.safeParse(playlist({ description: 'x'.repeat(200) + '…' })).success, true);
    assert.equal(watchPlaylistSchema.safeParse(playlist({ description: 'x'.repeat(200) + '...' })).success, false);
    const longVideo = video({ description: 'x'.repeat(500) + '…' });
    assert.equal(watchPlaylistSchema.safeParse(playlist({ videos: [longVideo] })).success, true);
    const tooLong = video({ description: 'x'.repeat(502) });
    assert.equal(watchPlaylistSchema.safeParse(playlist({ videos: [tooLong] })).success, false);
  });

  test('rejects a bad video id, a non-YouTube cover host, a bad date or an unknown key', () => {
    const bad: WatchVideo[] = [
      video({ id: 'short' }),
      video({ cover: { src: 'https://example.org/x.jpg', srcset: '' } }),
      video({ publishedIso: 'November 3, 2025' }),
      { ...video(), publishedText: 'November 3, 2025' } as WatchVideo,
    ];
    for (const v of bad) {
      assert.equal(watchPlaylistSchema.safeParse(playlist({ videos: [v] })).success, false, JSON.stringify(v));
    }
  });

  test('rejects none as a data mode', () => {
    assert.equal(watchPlaylistSchema.safeParse({ ...playlist(), dataMode: 'none' }).success, false);
  });
});

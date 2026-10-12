import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { coverFrom, cutAtWord, failedPlaylist, normalizePlaylist, normalizeVideo, normalizeVideos } from './normalize';
import { watchPlaylistSchema, type CuratedPlaylist } from './schema';
import type { ApiPlaylistItem, ApiVideo } from './youtube';
import playlistsBody from './fixtures/api/playlists.json';
import alphaPage1 from './fixtures/api/playlistItems-alpha-1.json';
import alphaPage2 from './fixtures/api/playlistItems-alpha-2.json';
import bravoItems from './fixtures/api/playlistItems-bravo.json';
import videosBody from './fixtures/api/videos.json';

const videos = videosBody.items as ApiVideo[];
const alphaItems = [...alphaPage1.items, ...alphaPage2.items] as ApiPlaylistItem[];
const apiPlaylist = (id: string) => playlistsBody.items.find((p) => p.id === id)!;

const curated = (overrides: Partial<CuratedPlaylist> = {}): CuratedPlaylist => ({
  slug: 'alpha',
  playlist_id: 'PLfixtureAlpha01',
  order: 1,
  description: 'Editor copy.',
  max_videos: 50,
  ...overrides,
});

const item = (position: number, videoId: string): ApiPlaylistItem => ({ snippet: { position, resourceId: { videoId } } });
const template = videos.find((v) => v.id === 'fxAlpha0002')!;
const apiVideo = (id: string): ApiVideo => ({ ...template, id });

describe('normalizeVideos filters and order', () => {
  const result = normalizeVideos(alphaItems, videos, 50);

  test('keeps public and unlisted, processed, not live, embeddable videos in position order', () => {
    assert.deepEqual(result.videos.map((v) => v.id), ['fxAlpha0001', 'fxAlpha0002', 'fxAlpha0003']);
  });

  test('counts each dropped item by reason', () => {
    assert.deepEqual(result.droppedBy, {
      missing: 1,
      private: 1,
      live: 1,
      'not-embeddable': 1,
      duplicate: 1,
      'not-processed': 1,
    });
  });

  test('a non-embeddable video is dropped and counted as not embeddable', () => {
    const r = normalizeVideos([item(0, 'fxAlphaNoEm'), item(1, 'fxAlpha0001')], videos, 50);
    assert.deepEqual(r.videos.map((v) => v.id), ['fxAlpha0001']);
    assert.deepEqual(r.droppedBy, { 'not-embeddable': 1 });
  });

  test('de-duplicates by first position, not by response order', () => {
    const a = apiVideo('dupVideo001');
    const r = normalizeVideos([item(4, 'dupVideo001'), item(2, 'other000002'), item(1, 'dupVideo001')], [a, apiVideo('other000002')], 50);
    assert.deepEqual(r.videos.map((v) => v.id), ['dupVideo001', 'other000002']);
    assert.equal(r.droppedBy.duplicate, 1);
  });

  test('max_videos caps the kept list, and videos past it are not counted as dropped', () => {
    const r = normalizeVideos(alphaItems, videos, 2);
    assert.deepEqual(r.videos.map((v) => v.id), ['fxAlpha0001', 'fxAlpha0002']);
    assert.equal(Object.values(r.droppedBy).reduce((sum, n) => sum + n, 0), 6);
  });

  test('a video with no usable thumbnail, title, ID or date is dropped as invalid', () => {
    const base = apiVideo('goodVideo01');
    const bad: ApiVideo[] = [
      { ...base, id: 'badThumbs01', snippet: { ...base.snippet, thumbnails: { high: { url: 'https://example.org/x.jpg' } } } },
      { ...base, id: 'badTitle001', snippet: { ...base.snippet, title: '   ' } },
      { ...base, id: 'short' },
      { ...base, id: 'badDate0001', snippet: { ...base.snippet, publishedAt: 'yesterday' } },
    ];
    const r = normalizeVideos(bad.map((v, i) => item(i, v.id!)), bad, 50);
    assert.deepEqual(r.videos, []);
    assert.equal(r.droppedBy.invalid, 4);
  });

  test('a video that fails watchVideoSchema is dropped alone, not its playlist', () => {
    // Date.parse accepts a six-digit year, but the schema's ISO datetime does not.
    const odd = { ...apiVideo('farFuture01'), snippet: { ...template.snippet, publishedAt: '+010000-01-01T00:00:00Z' } };
    const r = normalizeVideos([item(0, 'farFuture01'), item(1, 'fxAlpha0001')], [odd, ...videos], 50);
    assert.deepEqual(r.videos.map((v) => v.id), ['fxAlpha0001']);
    assert.deepEqual(r.droppedBy, { invalid: 1 });
  });
});

describe('normalizeVideo fields', () => {
  const byId = (id: string) => normalizeVideo(videos.find((v) => v.id === id)!)!;

  test('frame tier is sd only when the API returned standard', () => {
    assert.equal(byId('fxAlpha0001').frameTier, 'sd');
    assert.equal(byId('fxAlpha0002').frameTier, 'mq');
  });

  test('durations as text, both empty when missing', () => {
    assert.equal(byId('fxAlpha0001').durationText, '22:58');
    assert.equal(byId('fxAlpha0001').durationSpoken, '22 minutes 58 seconds');
    assert.equal(byId('fxAlpha0002').durationText, '1:02:03');
    assert.equal(byId('fxAlpha0003').durationText, '');
    assert.equal(byId('fxAlpha0003').durationSpoken, '');
  });

  test('publishedIso is whole seconds with Z', () => {
    assert.equal(byId('fxAlpha0001').publishedIso, '2025-11-03T17:00:00Z');
    assert.equal(byId('fxAlpha0002').publishedIso, '2024-02-29T08:30:00Z');
  });

  test('the video channel is the video\'s own', () => {
    assert.equal(byId('fxAlpha0002').channel, 'Fixture Channel Three');
  });

  test('a long video description is cut at a word to 500 plus one ellipsis', () => {
    const d = byId('fxAlpha0003').description;
    assert.ok(d.length <= 501, String(d.length));
    assert.ok(d.length > 400);
    assert.ok(d.endsWith('…'));
    assert.match(d, /\S…$/);
  });
});

describe('coverFrom', () => {
  test('srcset is sorted by width and src prefers the 480w image', () => {
    const cover = coverFrom({
      maxres: { url: 'https://i.ytimg.com/vi/x/maxresdefault.jpg', width: 1280 },
      standard: { url: 'https://i.ytimg.com/vi/x/sddefault.jpg', width: 640 },
      medium: { url: 'https://i.ytimg.com/vi/x/mqdefault.jpg', width: 320 },
      high: { url: 'https://i.ytimg.com/vi/x/hqdefault.jpg', width: 480 },
      default: { url: 'https://i.ytimg.com/vi/x/default.jpg', width: 120 },
    });
    assert.deepEqual(cover, {
      src: 'https://i.ytimg.com/vi/x/hqdefault.jpg',
      srcset: [
        'https://i.ytimg.com/vi/x/mqdefault.jpg 320w',
        'https://i.ytimg.com/vi/x/hqdefault.jpg 480w',
        'https://i.ytimg.com/vi/x/sddefault.jpg 640w',
        'https://i.ytimg.com/vi/x/maxresdefault.jpg 1280w',
      ].join(', '),
    });
  });

  test('nominal widths fill in, and hosts other than i.ytimg.com are ignored', () => {
    const cover = coverFrom({
      medium: { url: 'https://i.ytimg.com/vi/x/mqdefault.jpg' },
      high: { url: 'http://i.ytimg.com/vi/x/hqdefault.jpg' },
      standard: { url: 'https://i.ytimg.com.evil.test/x.jpg' },
    });
    assert.deepEqual(cover, { src: 'https://i.ytimg.com/vi/x/mqdefault.jpg', srcset: 'https://i.ytimg.com/vi/x/mqdefault.jpg 320w' });
    assert.equal(coverFrom({ default: { url: 'https://i.ytimg.com/vi/x/default.jpg' } }), null);
    assert.equal(coverFrom(undefined), null);
  });
});

describe('cutAtWord', () => {
  test('short text is only trimmed', () => {
    assert.equal(cutAtWord('  short text \r\n', 200), 'short text');
  });

  test('cuts back to the last whole word', () => {
    assert.equal(cutAtWord('alpha beta gamma', 13), 'alpha beta…');
    assert.equal(cutAtWord('alpha beta gamma', 10), 'alpha beta…');
  });

  test('one long word is cut hard', () => {
    assert.equal(cutAtWord('x'.repeat(30), 10), 'x'.repeat(10) + '…');
  });

  test('never splits a surrogate pair', () => {
    const emoji = String.fromCodePoint(0x1f916);
    const cut = cutAtWord('x'.repeat(9) + emoji + 'yyyy', 10);
    assert.equal(cut, 'x'.repeat(9) + '…');
  });
});

describe('normalizePlaylist', () => {
  test('alpha: editor description, API name and creator, ok status, valid entry', () => {
    const r = normalizePlaylist({ curated: curated(), api: apiPlaylist('PLfixtureAlpha01'), items: alphaItems, videos, dataMode: 'fixture' });
    assert.equal(r.playlist.status, 'ok');
    assert.equal(r.playlist.name, 'Alpha fixture playlist');
    assert.equal(r.playlist.creator, 'Fixture Channel One');
    assert.equal(r.playlist.description, 'Editor copy.');
    assert.equal(r.dropped, 6);
    const parsed = watchPlaylistSchema.safeParse(r.playlist);
    assert.equal(parsed.success, true, parsed.error?.message);
  });

  test('bravo: every video filtered gives empty, and the API description is cut at a word to 200', () => {
    const { description: _omit, ...noDescription } = curated({ slug: 'bravo', playlist_id: 'PLfixtureBravo02', order: 2 });
    const api = apiPlaylist('PLfixtureBravo02');
    const r = normalizePlaylist({ curated: noDescription, api, items: bravoItems.items, videos, dataMode: 'fixture' });
    assert.equal(r.playlist.status, 'empty');
    assert.deepEqual(r.playlist.videos, []);
    assert.deepEqual(r.droppedBy, { private: 1, 'not-embeddable': 1 });
    const d = r.playlist.description;
    assert.ok(api.snippet.description.length > 200);
    assert.ok(d.length <= 201, String(d.length));
    assert.ok(d.endsWith('…'));
    const kept = d.slice(0, -1);
    assert.ok(api.snippet.description.startsWith(kept));
    assert.match(api.snippet.description.slice(kept.length), /^\s/, 'cut lands before a space, not mid-word');
    assert.equal(watchPlaylistSchema.safeParse(r.playlist).success, true);
  });

  test('the dropped total leaves out videos trimmed by max_videos', () => {
    const r = normalizePlaylist({ curated: curated({ max_videos: 1 }), api: apiPlaylist('PLfixtureAlpha01'), items: alphaItems, videos, dataMode: 'fixture' });
    assert.equal(r.playlist.videos.length, 1);
    assert.equal(r.dropped, 6);
  });

  test('a YAML creator wins over the API channel', () => {
    const r = normalizePlaylist({ curated: curated({ creator: 'Editor Name' }), api: apiPlaylist('PLfixtureAlpha01'), items: [], videos: [], dataMode: 'live' });
    assert.equal(r.playlist.creator, 'Editor Name');
    assert.equal(r.playlist.dataMode, 'live');
  });

  test('failed: no videos, and no creator key when the API channel is empty', () => {
    const p = failedPlaylist(curated({ slug: 'charlie', playlist_id: 'PLfixtureCharlie3', order: 3 }), apiPlaylist('PLfixtureCharlie3'), 'fixture');
    assert.equal(p.status, 'failed');
    assert.deepEqual(p.videos, []);
    assert.equal('creator' in p, false);
    const parsed = watchPlaylistSchema.safeParse(p);
    assert.equal(parsed.success, true, parsed.error?.message);
  });
});

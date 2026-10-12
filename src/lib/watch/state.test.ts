import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { parseUrl, toSearch, type UrlPlaylist } from './state';
import type { WatchState } from './types';

const ALPHA_1 = 'aaaaaaaaaa1';
const ALPHA_2 = 'aaaaaaaaaa2';
const BRAVO_1 = 'bbbbbbbbbb1';
const SHARED = 'sssssssssss';

const playlists: UrlPlaylist[] = [
  { slug: 'alpha', videos: [{ id: ALPHA_1 }, { id: ALPHA_2 }] },
  { slug: 'bravo', videos: [{ id: BRAVO_1 }, { id: SHARED }] },
  { slug: 'charlie', videos: [{ id: SHARED }] },
  { slug: 'empty', videos: [] },
];

describe('parseUrl arrival rules (UI spec § 4.8)', () => {
  test('no query: first playlist, its first video as poster, nothing loaded', () => {
    assert.deepEqual(parseUrl('', playlists), {
      selectedSlug: 'alpha',
      video: { slug: 'alpha', id: ALPHA_1 },
      loaded: false,
      notice: false,
    });
  });

  test('known list selects that tab and shows its first video', () => {
    assert.deepEqual(parseUrl('?list=bravo', playlists), {
      selectedSlug: 'bravo',
      video: { slug: 'bravo', id: BRAVO_1 },
      loaded: false,
      notice: false,
    });
  });

  test('known list and v in it: poster of that video, counts as loaded', () => {
    assert.deepEqual(parseUrl('?list=alpha&v=' + ALPHA_2, playlists), {
      selectedSlug: 'alpha',
      video: { slug: 'alpha', id: ALPHA_2 },
      loaded: true,
      notice: false,
    });
  });

  test('v without list: the first playlist containing it', () => {
    assert.deepEqual(parseUrl('?v=' + SHARED, playlists), {
      selectedSlug: 'bravo',
      video: { slug: 'bravo', id: SHARED },
      loaded: true,
      notice: false,
    });
  });

  test('known list wins over an earlier playlist holding the same v', () => {
    const state = parseUrl(`?list=charlie&v=${SHARED}`, playlists);
    assert.equal(state.selectedSlug, 'charlie');
    assert.deepEqual(state.video, { slug: 'charlie', id: SHARED });
    assert.equal(state.loaded, true);
  });

  test('unknown list: first playlist, and the rewritten URL drops it', () => {
    const state = parseUrl('?list=nope', playlists);
    assert.equal(state.selectedSlug, 'alpha');
    assert.equal(state.notice, false);
    assert.equal(toSearch(state), '?list=alpha');
  });

  test('unknown list with a known v: v finds its playlist', () => {
    const state = parseUrl(`?list=nope&v=${BRAVO_1}`, playlists);
    assert.deepEqual(state.video, { slug: 'bravo', id: BRAVO_1 });
    assert.equal(state.loaded, true);
    assert.equal(toSearch(state), `?list=bravo&v=${BRAVO_1}`);
  });

  test('unknown v: first video of the playlist, notice, not loaded, URL drops v', () => {
    const state = parseUrl('?list=bravo&v=zzzzzzzzzzz', playlists);
    assert.deepEqual(state, {
      selectedSlug: 'bravo',
      video: { slug: 'bravo', id: BRAVO_1 },
      loaded: false,
      notice: true,
    });
    assert.equal(toSearch(state), '?list=bravo');
  });

  test('v that exists only in another playlist is unknown for the named list', () => {
    const state = parseUrl(`?list=alpha&v=${BRAVO_1}`, playlists);
    assert.equal(state.selectedSlug, 'alpha');
    assert.deepEqual(state.video, { slug: 'alpha', id: ALPHA_1 });
    assert.equal(state.loaded, false);
    assert.equal(state.notice, true);
  });

  test('unknown v with no list: first playlist and the notice', () => {
    const state = parseUrl('?v=zzzzzzzzzzz', playlists);
    assert.equal(state.selectedSlug, 'alpha');
    assert.equal(state.notice, true);
    assert.equal(state.loaded, false);
  });

  test('a playlist with no videos is selectable and has no poster', () => {
    assert.deepEqual(parseUrl('?list=empty', playlists), {
      selectedSlug: 'empty',
      video: null,
      loaded: false,
      notice: false,
    });
  });

  test('an empty v is treated as absent, with no notice', () => {
    const state = parseUrl('?list=bravo&v=', playlists);
    assert.equal(state.notice, false);
    assert.equal(state.loaded, false);
  });

  test('no playlists at all does not throw', () => {
    assert.deepEqual(parseUrl('?list=alpha&v=' + ALPHA_1, []), {
      selectedSlug: '',
      video: null,
      loaded: false,
      notice: true,
    });
  });
});

describe('toSearch', () => {
  test('before a video is loaded the URL follows the selected tab, no v', () => {
    const state: WatchState = { selectedSlug: 'bravo', video: { slug: 'alpha', id: ALPHA_1 }, loaded: false, notice: false };
    assert.equal(toSearch(state), '?list=bravo');
  });

  test('after a video is loaded the URL names it, whatever tab is shown', () => {
    const state: WatchState = { selectedSlug: 'charlie', video: { slug: 'alpha', id: ALPHA_2 }, loaded: true, notice: false };
    assert.equal(toSearch(state), `?list=alpha&v=${ALPHA_2}`);
  });

  test('nothing selected gives an empty query', () => {
    assert.equal(toSearch({ selectedSlug: '', video: null, loaded: false, notice: false }), '');
  });

  test('round trip: every state without a notice survives toSearch then parseUrl', () => {
    const states: WatchState[] = [
      { selectedSlug: 'alpha', video: { slug: 'alpha', id: ALPHA_1 }, loaded: false, notice: false },
      { selectedSlug: 'bravo', video: { slug: 'bravo', id: BRAVO_1 }, loaded: false, notice: false },
      { selectedSlug: 'empty', video: null, loaded: false, notice: false },
      { selectedSlug: 'alpha', video: { slug: 'alpha', id: ALPHA_2 }, loaded: true, notice: false },
      { selectedSlug: 'charlie', video: { slug: 'charlie', id: SHARED }, loaded: true, notice: false },
    ];
    for (const state of states) {
      assert.deepEqual(parseUrl(toSearch(state), playlists), state, toSearch(state));
    }
  });
});

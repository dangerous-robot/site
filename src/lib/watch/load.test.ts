import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import yaml from 'js-yaml';
import { createConsoleLog, escapeWorkflowCommand, loadWatchData, validateEntry, type WatchLog } from './load';
import { createWatchClient, CURATED_PATHS, resolveMode } from './env';
import { createFixtureFetch, fixtureFetch, reply, type FixtureGlobalError } from './fixtureFetch';
import { curatedFileSchema, watchPlaylistSchema, type CuratedPlaylist } from './schema';
import { createYouTubeClient, type FetchLike, type YouTubeClient } from './youtube';
import type { WatchPlaylist } from './types';

const KEY = 'zzTestKeyMarker-7Q2';

const fixtureCurated: CuratedPlaylist[] = curatedFileSchema.parse(
  // CURATED_PATHS is repo-relative; resolve it from here so the test does not depend on the working directory.
  yaml.load(readFileSync(new URL(`../../../${CURATED_PATHS.fixture}`, import.meta.url), 'utf8')),
).playlists;

/** Records exactly what reaches the console, through the real sink. */
function recordingConsole(githubActions = false) {
  const out: { stream: 'log' | 'warn'; line: string }[] = [];
  const log: WatchLog = createConsoleLog({ githubActions }, {
    log: (line: string) => out.push({ stream: 'log', line }),
    warn: (line: string) => out.push({ stream: 'warn', line }),
  });
  return {
    log,
    out,
    info: () => out.filter((o) => o.stream === 'log' && o.line.startsWith('[watch loader] ')).map((o) => o.line),
    warnings: () => out.filter((o) => o.stream === 'warn').map((o) => o.line),
    annotations: () => out.filter((o) => o.line.startsWith('::warning')).map((o) => o.line),
  };
}

const sleep = async () => {};
const fixtureClient = (globalError?: FixtureGlobalError) =>
  createYouTubeClient({ key: KEY, fetch: createFixtureFetch({ globalError }), sleep });
const fixtureEnv = { mode: 'fixture' as const, key: null, expectKey: false };
const liveEnv = { mode: 'live' as const, key: KEY, expectKey: true };

/** Wraps the fixture fetch so one call can be overridden. */
function overriding(match: (url: URL) => { status: number; body: unknown } | null): FetchLike {
  return async (raw, init) => {
    const override = match(new URL(raw));
    return override ? reply(override.status, override.body) : fixtureFetch(raw, init);
  };
}

describe('fixture load', async () => {
  const con = recordingConsole();
  const result = await loadWatchData({
    curated: fixtureCurated,
    client: await createWatchClient(resolveMode({ WATCH_DATA: 'fixture' })),
    env: fixtureEnv,
    log: con.log,
  });

  test('info lines in the fixed format, in curated order', () => {
    assert.deepEqual(con.info(), [
      '[watch loader] fetched PLfixtureAlpha01: 3 videos (dropped: 6, not embeddable: 1)',
      '[watch loader] fetched PLfixtureBravo02: 0 videos (dropped: 2, not embeddable: 1)',
      '[watch loader] skipped PLfixtureDelta04: not returned by playlists.list',
      '[watch loader] mode=fixture playlists=3 videos=3',
    ]);
  });

  test('Alpha ok, Bravo empty, Charlie failed, Delta omitted; every entry validates', () => {
    assert.equal(result.mode, 'fixture');
    assert.deepEqual(result.playlists.map((p) => [p.slug, p.status, p.videos.length]), [
      ['alpha', 'ok', 3],
      ['bravo', 'empty', 0],
      ['charlie', 'failed', 0],
    ]);
    for (const p of result.playlists) {
      assert.equal(p.dataMode, 'fixture');
      assert.equal(watchPlaylistSchema.safeParse(p).success, true, p.slug);
    }
  });

  test('Charlie 404 gives a warning with call, ID, status, reason and the API message', () => {
    const charlie = con.warnings().filter((w) => w.includes('PLfixtureCharlie3'));
    assert.equal(charlie.length, 1);
    assert.match(charlie[0], /^\[watch loader\] warning: playlistItems\.list failed for PLfixtureCharlie3 \(404 playlistNotFound\): The playlist identified/);
  });

  test('Delta missing from playlists.list gives a warning and a skipped line', () => {
    assert.equal(con.warnings().filter((w) => w.includes('PLfixtureDelta04')).length, 1);
    assert.equal(result.warnings.length, 2);
  });

  test('log lines carry no API titles', () => {
    for (const { line } of con.out) assert.doesNotMatch(line, /(Alpha|Bravo|Charlie) fixture playlist|Fixture video/, line);
  });
});

describe('API calls (quota)', () => {
  function recordingFixture() {
    const calls: string[] = [];
    const fetch: FetchLike = (raw, init) => {
      const url = new URL(raw);
      const p = url.searchParams;
      calls.push(`${url.pathname.split('/').pop()} ${p.get('playlistId') ?? p.get('id')}${p.get('pageToken') ? ' p2' : ''}`);
      return fixtureFetch(raw, init);
    };
    return { calls, client: createYouTubeClient({ key: KEY, fetch, sleep }) };
  }

  test('first pages for every playlist, one batched videos call, then a second page only for a playlist short of max_videos', async () => {
    const { calls, client } = recordingFixture();
    await loadWatchData({ curated: fixtureCurated, client, env: fixtureEnv, log: recordingConsole().log });
    assert.deepEqual(calls, [
      'playlists PLfixtureAlpha01,PLfixtureBravo02,PLfixtureCharlie3,PLfixtureDelta04',
      'playlistItems PLfixtureAlpha01',
      'playlistItems PLfixtureBravo02',
      'playlistItems PLfixtureCharlie3',
      'videos fxAlpha0001,fxAlphaDel1,fxAlphaPriv,fxAlphaLive,fxAlphaNoEm,fxBravoPriv,fxBravoNoEm',
      'playlistItems PLfixtureAlpha01 p2',
      'videos fxAlpha0003,fxAlpha0002,fxAlphaProc',
    ]);
  });

  test('a playlist that reaches max_videos on its first page fetches no more pages', async () => {
    const { calls, client } = recordingFixture();
    const curated = fixtureCurated.map((c) => (c.slug === 'alpha' ? { ...c, max_videos: 1 } : c));
    const result = await loadWatchData({ curated, client, env: fixtureEnv, log: recordingConsole().log });
    assert.equal(calls.some((c) => c.endsWith(' p2')), false);
    assert.deepEqual(result.playlists[0].videos.map((v) => v.id), ['fxAlpha0001']);
  });
});

describe('per-playlist failures', () => {
  test('a playlistItems 403 that is not a key error marks only that playlist failed', async () => {
    const forbidden = { error: { code: 403, message: 'The fixture playlist is private.', errors: [{ reason: 'forbidden' }] } };
    const fetch = overriding((url) =>
      url.pathname.endsWith('/playlistItems') && url.searchParams.get('playlistId') === 'PLfixtureAlpha01' ? { status: 403, body: forbidden } : null);
    const con = recordingConsole();
    const result = await loadWatchData({ curated: fixtureCurated, client: createYouTubeClient({ key: KEY, fetch, sleep }), env: fixtureEnv, log: con.log });
    assert.equal(result.mode, 'fixture');
    assert.deepEqual(result.playlists.map((p) => [p.slug, p.status]), [['alpha', 'failed'], ['bravo', 'empty'], ['charlie', 'failed']]);
    assert.match(con.warnings()[0], /playlistItems\.list failed for PLfixtureAlpha01 \(403 forbidden\): The fixture playlist is private\. Showing the playlist as failed\./);
  });

  const alphaPage2 = (url: URL) =>
    url.pathname.endsWith('/playlistItems') && url.searchParams.get('playlistId') === 'PLfixtureAlpha01' && url.searchParams.has('pageToken');

  for (const [name, failure, status] of [
    ['a 400 invalidPageToken', { status: 400, body: { error: { code: 400, message: 'The request specifies an invalid page token.', errors: [{ reason: 'invalidPageToken' }] } } }, '400 invalidPageToken'],
    ['a 5xx after the retries', { status: 503, body: 'busy' }, '503 network'],
  ] as const) {
    test(`${name} on one playlist's second page marks only that playlist failed`, async () => {
      const fetch = overriding((url) => (alphaPage2(url) ? failure : null));
      const con = recordingConsole();
      const result = await loadWatchData({ curated: fixtureCurated, client: createYouTubeClient({ key: KEY, fetch, sleep }), env: fixtureEnv, log: con.log });
      assert.equal(result.mode, 'fixture');
      assert.deepEqual(result.playlists.map((p) => [p.slug, p.status, p.videos.length]), [['alpha', 'failed', 0], ['bravo', 'empty', 0], ['charlie', 'failed', 0]]);
      assert.match(con.warnings()[0], new RegExp(`playlistItems\\.list failed for PLfixtureAlpha01 \\(${status}\\).* Showing the playlist as failed\\.$`));
      assert.deepEqual(con.info(), [
        '[watch loader] fetched PLfixtureBravo02: 0 videos (dropped: 2, not embeddable: 1)',
        '[watch loader] skipped PLfixtureDelta04: not returned by playlists.list',
        '[watch loader] mode=fixture playlists=3 videos=0',
      ]);
    });
  }

  test('a quota error on one playlist\'s second page is still global', async () => {
    const fetch = overriding((url) => (alphaPage2(url) ? { status: 403, body: { error: { code: 403, message: 'Quota gone.', errors: [{ reason: 'quotaExceeded' }] } } } : null));
    const con = recordingConsole();
    const result = await loadWatchData({ curated: fixtureCurated, client: createYouTubeClient({ key: KEY, fetch, sleep }), env: fixtureEnv, log: con.log });
    assert.equal(result.mode, 'none');
    assert.deepEqual(result.playlists, []);
    assert.match(result.warnings[0], /^playlistItems\.list failed for PLfixtureAlpha01 \(403 quotaExceeded\): Quota gone\. Rendering the empty state\.$/);
  });
});

describe('global errors', () => {
  test('a 403 quotaExceeded gives mode none and one warning, and nothing throws', async () => {
    const con = recordingConsole();
    const result = await loadWatchData({ curated: fixtureCurated, client: fixtureClient('quota'), env: fixtureEnv, log: con.log });
    assert.deepEqual(result, { mode: 'none', playlists: [], warnings: result.warnings });
    assert.equal(result.warnings.length, 1);
    assert.match(result.warnings[0], /^playlists\.list failed \(403 quotaExceeded\): .* Rendering the empty state\.$/);
  });

  for (const [mode, status, reason, message] of [
    ['key-invalid', 400, 'keyInvalid', 'API key not valid. Please pass a valid API key.'],
    ['referer', 403, 'forbidden', 'Requests from referer <empty> are blocked.'],
  ] as const) {
    test(`a ${reason} key rejection: one warning, skipped lines, mode=none, no key text`, async () => {
      const con = recordingConsole(true);
      const result = await loadWatchData({ curated: fixtureCurated, client: fixtureClient(mode), env: liveEnv, log: con.log });
      assert.equal(result.mode, 'none');
      assert.deepEqual(con.warnings(), [
        `[watch loader] warning: playlists.list failed (${status} ${reason}): ${message} Rendering the empty state.`,
      ]);
      assert.deepEqual(con.info(), [
        ...fixtureCurated.map((c) => `[watch loader] skipped ${c.playlist_id}: global API error (${reason})`),
        '[watch loader] mode=none playlists=0 videos=0',
      ]);
      assert.deepEqual(con.annotations(), [
        `::warning title=Watch page::playlists.list failed (${status} ${reason}): ${message} Rendering the empty state.`,
      ]);
      for (const { line } of con.out) assert.equal(line.includes(KEY), false, line);
    });
  }

  test('an API message with a newline and % comes out as one annotation line', async () => {
    const body = { error: { code: 403, message: 'Requests from referer <empty> are blocked.\n100% sure.', errors: [{ reason: 'forbidden' }] } };
    const con = recordingConsole(true);
    const client = createYouTubeClient({ key: KEY, fetch: overriding(() => ({ status: 403, body })), sleep });
    await loadWatchData({ curated: fixtureCurated, client, env: liveEnv, log: con.log });
    const [annotation] = con.annotations();
    assert.equal(annotation, '::warning title=Watch page::playlists.list failed (403 forbidden): Requests from referer <empty> are blocked.%0A100%25 sure. Rendering the empty state.');
    assert.equal(annotation.includes('\n'), false);
  });

  test('without GITHUB_ACTIONS there is no annotation', async () => {
    const con = recordingConsole(false);
    await loadWatchData({ curated: fixtureCurated, client: fixtureClient('quota'), env: fixtureEnv, log: con.log });
    assert.deepEqual(con.annotations(), []);
  });

  test('a global error part way through drops the fetched lines already made', async () => {
    // Alpha's second-page videos call comes after every playlist's first page has loaded.
    const fetch = overriding((url) =>
      url.pathname.endsWith('/videos') && url.searchParams.get('id')?.startsWith('fxAlpha0003')
        ? { status: 403, body: { error: { code: 403, message: 'Quota gone.', errors: [{ reason: 'quotaExceeded' }] } } }
        : null);
    const con = recordingConsole();
    const result = await loadWatchData({ curated: fixtureCurated, client: createYouTubeClient({ key: KEY, fetch, sleep }), env: fixtureEnv, log: con.log });
    assert.equal(result.mode, 'none');
    assert.equal(con.info().some((l) => l.includes('fetched')), false);
    assert.equal(con.info().at(-1), '[watch loader] mode=none playlists=0 videos=0');
  });

  test('a network failure that quotes the URL leaks no key into warnings', async () => {
    const fetch: FetchLike = async (url) => { throw new Error(`request to ${url} failed`); };
    const con = recordingConsole(true);
    const result = await loadWatchData({ curated: fixtureCurated, client: createYouTubeClient({ key: KEY, fetch, sleep }), env: liveEnv, log: con.log });
    assert.equal(result.mode, 'none');
    assert.match(result.warnings[0], /network/);
    for (const { line } of con.out) assert.equal(line.includes(KEY), false, line);
  });

  test('an unexpected error from the client still gives mode none, not a throw', async () => {
    const broken: YouTubeClient = {
      listPlaylists: async () => { throw new Error(`bug with ${KEY} in it`); },
      listPlaylistItemsPage: async () => ({ items: [], nextPageToken: null }),
      listVideos: async () => [],
    };
    const con = recordingConsole();
    const result = await loadWatchData({ curated: fixtureCurated, client: broken, env: liveEnv, log: con.log });
    assert.equal(result.mode, 'none');
    assert.match(result.warnings[0], /^watch data load failed: bug with \[redacted\] in it\. Rendering the empty state\.$/);
    assert.equal(con.info().at(-2), '[watch loader] skipped PLfixtureDelta04: global API error (unexpected error)');
  });
});

describe('none mode', () => {
  test('with WATCH_EXPECT_KEY=1: the missing-key warning, then the summary', async () => {
    const con = recordingConsole();
    const env = resolveMode({ WATCH_EXPECT_KEY: '1', YOUTUBE_API_KEY: '' });
    const result = await loadWatchData({ curated: fixtureCurated, client: await createWatchClient(env), env, log: con.log });
    assert.deepEqual(result, { mode: 'none', playlists: [], warnings: ['YOUTUBE_API_KEY is not set, so the watch page renders the empty state.'] });
    assert.deepEqual(con.info(), ['[watch loader] mode=none playlists=0 videos=0']);
  });

  test('without it: no warning', async () => {
    const con = recordingConsole();
    const env = resolveMode({});
    const result = await loadWatchData({ curated: fixtureCurated, client: null, env, log: con.log });
    assert.deepEqual(result.warnings, []);
    assert.deepEqual(con.out.map((o) => o.line), ['[watch loader] mode=none playlists=0 videos=0']);
  });
});

describe('schema check per entry (build safety)', () => {
  const valid: WatchPlaylist = {
    slug: 'alpha', youtubeId: 'PLfixtureAlpha01', order: 1, name: 'Alpha', description: '',
    status: 'empty', dataMode: 'fixture', videos: [],
  };

  test('validateEntry passes a valid entry and names the first issue of a bad one', () => {
    assert.equal(validateEntry(valid), null);
    assert.match(validateEntry({ ...valid, slug: 'Not A Slug' }) ?? '', /^slug: slug must be kebab-case/);
  });

  test('an entry that fails the schema is dropped with a warning and the rest survive', async () => {
    const curated = fixtureCurated.map((c) => (c.slug === 'bravo' ? { ...c, slug: 'Bravo Bad Slug' } : c));
    const con = recordingConsole();
    const result = await loadWatchData({ curated, client: fixtureClient(), env: fixtureEnv, log: con.log });
    assert.equal(result.mode, 'fixture');
    assert.deepEqual(result.playlists.map((p) => p.slug), ['alpha', 'charlie']);
    const bravo = con.warnings().filter((w) => w.includes('PLfixtureBravo02'));
    assert.deepEqual(bravo, ['[watch loader] warning: playlist PLfixtureBravo02 failed the schema check (slug: slug must be kebab-case: lowercase letters, digits and single hyphens); leaving it off the page.']);
    assert.ok(con.info().includes('[watch loader] skipped PLfixtureBravo02: failed the schema check'));
    assert.equal(con.info().at(-1), '[watch loader] mode=fixture playlists=2 videos=3');
  });
});

describe('escapeWorkflowCommand', () => {
  test('escapes % first, then CR and LF', () => {
    assert.equal(escapeWorkflowCommand('50%\r\n%0A'), '50%25%0D%0A%250A');
  });
});

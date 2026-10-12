import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { createYouTubeClient, FIELDS, redact, YouTubeError, type FetchLike } from './youtube';
import quotaBody from './fixtures/api/error-quota.json';
import refererBody from './fixtures/api/error-referer-blocked.json';
import keyInvalidBody from './fixtures/api/error-key-invalid.json';
import notFoundBody from './fixtures/api/error-playlist-not-found.json';

// Distinctive so a leak is easy to find; deliberately not shaped like a real
// Google key, so a repo-wide scan for real keys stays clean.
const KEY = 'zzTestKeyMarker-7Q2';

type Reply = { status: number; body: unknown } | Error;

interface Recorded {
  url: URL;
  init: Record<string, unknown>;
  argCount: number;
}

function fakeFetch(handler: (url: URL, n: number) => Reply) {
  const calls: Recorded[] = [];
  const fetch: FetchLike = async (...args: unknown[]) => {
    const [raw, init] = args as [string, Record<string, unknown>];
    const url = new URL(raw);
    calls.push({ url, init, argCount: args.length });
    const reply = handler(url, calls.length);
    if (reply instanceof Error) throw reply;
    const text = typeof reply.body === 'string' ? reply.body : JSON.stringify(reply.body);
    return { status: reply.status, text: async () => text };
  };
  return { fetch, calls };
}

function client(handler: (url: URL, n: number) => Reply) {
  const sleeps: number[] = [];
  const f = fakeFetch(handler);
  const yt = createYouTubeClient({ key: KEY, fetch: f.fetch, sleep: async (ms) => { sleeps.push(ms); } });
  return { yt, calls: f.calls, sleeps };
}

async function caught(promise: Promise<unknown>): Promise<YouTubeError> {
  try {
    await promise;
  } catch (err) {
    assert.ok(err instanceof YouTubeError, `expected a YouTubeError, got ${String(err)}`);
    return err;
  }
  assert.fail('expected a rejection');
}

const ok = (body: unknown): Reply => ({ status: 200, body });
const items = (prefix: string, n: number) =>
  Array.from({ length: n }, (_, i) => ({ snippet: { position: i, resourceId: { videoId: `${prefix}${i}` } } }));

describe('listPlaylistItemsPage pagination (U2)', () => {
  test('passes the page token and returns the next one, null on the last page', async () => {
    const pages: Record<string, Reply> = {
      '': ok({ items: items('a', 2), nextPageToken: 'p2' }),
      p2: ok({ items: items('b', 1), nextPageToken: '' }),
    };
    const { yt, calls } = client((url) => pages[url.searchParams.get('pageToken') ?? '']);
    const first = await yt.listPlaylistItemsPage('PLfixtureAlpha01');
    assert.equal(first.items.length, 2);
    assert.equal(first.nextPageToken, 'p2');
    const last = await yt.listPlaylistItemsPage('PLfixtureAlpha01', 'p2');
    assert.equal(last.items.length, 1);
    assert.equal(last.nextPageToken, null);
    assert.deepEqual(calls.map((c) => c.url.searchParams.get('pageToken')), [null, 'p2']);
    for (const c of calls) {
      assert.equal(c.url.pathname, '/youtube/v3/playlistItems');
      assert.equal(c.url.searchParams.get('playlistId'), 'PLfixtureAlpha01');
      assert.equal(c.url.searchParams.get('maxResults'), '50');
    }
  });

  test('fields keeps nextPageToken, or the real API would stop after one page', async () => {
    const { yt, calls } = client(() => ok({ items: [] }));
    await yt.listPlaylistItemsPage('PLfixtureAlpha01');
    const fields = calls[0].url.searchParams.get('fields') ?? '';
    assert.equal(fields, FIELDS.playlistItems);
    assert.match(fields, /^nextPageToken,/);
    assert.match(fields, /position/);
    assert.match(fields, /videoId/);
  });
});

describe('batched calls (U3)', () => {
  test('listPlaylists makes one call for all IDs', async () => {
    const ids = ['PLfixtureAlpha01', 'PLfixtureBravo02', 'PLfixtureCharlie3'];
    const { yt, calls } = client(() => ok({ items: [{ id: 'PLfixtureAlpha01' }] }));
    const result = await yt.listPlaylists(ids);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url.pathname, '/youtube/v3/playlists');
    assert.equal(calls[0].url.searchParams.get('id'), ids.join(','));
    assert.equal(calls[0].url.searchParams.get('part'), 'snippet');
    assert.equal(calls[0].url.searchParams.get('fields'), FIELDS.playlists);
    assert.equal(result.length, 1);
  });

  test('listVideos batches IDs by 50 and asks for snippet, contentDetails and status', async () => {
    const ids = Array.from({ length: 120 }, (_, i) => `vid${String(i).padStart(8, '0')}`);
    const { yt, calls } = client((url) => ok({ items: (url.searchParams.get('id') ?? '').split(',').map((id) => ({ id })) }));
    const result = await yt.listVideos(ids);
    assert.deepEqual(calls.map((c) => c.url.searchParams.get('id')?.split(',').length), [50, 50, 20]);
    assert.deepEqual(result.map((v) => v.id), ids);
    for (const c of calls) {
      assert.equal(c.url.pathname, '/youtube/v3/videos');
      assert.equal(c.url.searchParams.get('part'), 'snippet,contentDetails,status');
      const fields = c.url.searchParams.get('fields') ?? '';
      assert.match(fields, /snippet\([^)]*liveBroadcastContent/);
      assert.match(fields, /status\(privacyStatus,uploadStatus,embeddable\)/);
    }
  });

  test('requests carry only the documented query parameters', async () => {
    const { yt, calls } = client(() => ok({ items: [] }));
    await yt.listPlaylists(['PLfixtureAlpha01']);
    await yt.listPlaylistItemsPage('PLfixtureAlpha01', 'p2');
    await yt.listVideos(['fxAlpha0001']);
    const allowed = new Set(['key', 'part', 'fields', 'id', 'playlistId', 'maxResults', 'pageToken']);
    for (const c of calls) {
      for (const name of c.url.searchParams.keys()) assert.ok(allowed.has(name), name);
      assert.equal(c.url.searchParams.get('key'), KEY);
    }
  });
});

describe('no headers on any request (U18)', () => {
  test('fetch gets the URL and an AbortSignal only', async () => {
    const { yt, calls } = client(() => ok({ items: [], nextPageToken: '' }));
    await yt.listPlaylists(['PLfixtureAlpha01']);
    await yt.listPlaylistItemsPage('PLfixtureAlpha01');
    await yt.listVideos(['fxAlpha0001']);
    assert.equal(calls.length, 3);
    for (const c of calls) {
      assert.equal(c.argCount, 2);
      assert.deepEqual(Object.keys(c.init), ['signal']);
      assert.ok(c.init.signal instanceof AbortSignal);
    }
  });
});

describe('error mapping (U5, U19)', () => {
  test('a 403 quotaExceeded is global and not retried (U5)', async () => {
    const { yt, calls, sleeps } = client(() => ({ status: 403, body: quotaBody }));
    const err = await caught(yt.listPlaylists(['PLfixtureAlpha01']));
    assert.equal(err.kind, 'quota');
    assert.equal(err.scope, 'global');
    assert.equal(err.reason, 'quotaExceeded');
    assert.equal(calls.length, 1);
    assert.deepEqual(sleeps, []);
  });

  test('a 403 referer-blocked body is a global key error with the verbatim message (U19)', async () => {
    const { yt } = client(() => ({ status: 403, body: refererBody }));
    const err = await caught(yt.listPlaylists(['PLfixtureAlpha01']));
    assert.equal(err.kind, 'key');
    assert.equal(err.scope, 'global');
    assert.equal(err.status, 403);
    assert.equal(err.reason, 'forbidden');
    assert.equal(err.apiMessage, 'Requests from referer <empty> are blocked.');
    assert.equal(err.message, 'playlists.list failed (403 forbidden): Requests from referer <empty> are blocked.');
  });

  test('a 400 keyInvalid is a key error by reason, whatever the status (U19)', async () => {
    const { yt } = client(() => ({ status: 400, body: keyInvalidBody }));
    const err = await caught(yt.listPlaylistItemsPage('PLfixtureAlpha01'));
    assert.equal(err.kind, 'key');
    assert.equal(err.scope, 'global');
    assert.equal(err.reason, 'keyInvalid');
    assert.match(err.message, /\(400 keyInvalid\): API key not valid/);
  });

  test('playlistItems 404 and plain 403 are about one playlist', async () => {
    const forbidden = { error: { code: 403, message: 'The fixture playlist is private.', errors: [{ reason: 'forbidden' }] } };
    for (const [status, body, kind] of [[404, notFoundBody, 'not-found'], [403, forbidden, 'forbidden']] as const) {
      const { yt } = client(() => ({ status, body }));
      const err = await caught(yt.listPlaylistItemsPage('PLfixtureCharlie3'));
      assert.equal(err.kind, kind);
      assert.equal(err.scope, 'playlist');
      assert.equal(err.playlistId, 'PLfixtureCharlie3');
      assert.match(err.message, /^playlistItems\.list failed for PLfixtureCharlie3 \(/);
    }
  });

  test('the same errors on a batched call are global', async () => {
    const { yt } = client(() => ({ status: 404, body: notFoundBody }));
    const err = await caught(yt.listVideos(['fxAlpha0001']));
    assert.equal(err.scope, 'global');
  });

  test('5xx is retried twice with backoff, then succeeds', async () => {
    const { yt, calls, sleeps } = client((_url, n) => (n <= 2 ? { status: 503, body: 'busy' } : ok({ items: [{ id: 'x' }] })));
    const result = await yt.listPlaylists(['PLfixtureAlpha01']);
    assert.equal(result.length, 1);
    assert.equal(calls.length, 3);
    assert.deepEqual(sleeps, [1000, 2000]);
  });

  test('5xx after the retries is a global network error', async () => {
    const { yt, calls } = client(() => ({ status: 500, body: '<html>oops</html>' }));
    const err = await caught(yt.listPlaylists(['PLfixtureAlpha01']));
    assert.equal(calls.length, 3);
    assert.equal(err.kind, 'network');
    assert.equal(err.scope, 'global');
    assert.equal(err.status, 500);
  });

  test('a thrown fetch is retried, then a global network error with status 0', async () => {
    const { yt, calls } = client(() => new TypeError('fetch failed'));
    const err = await caught(yt.listPlaylists(['PLfixtureAlpha01']));
    assert.equal(calls.length, 3);
    assert.equal(err.kind, 'network');
    assert.equal(err.status, 0);
    assert.equal(err.message, 'playlists.list failed (network): fetch failed');
  });

  test('malformed JSON on a 200 is global and not retried', async () => {
    for (const body of ['not json', { noItems: true }]) {
      const { yt, calls } = client(() => ({ status: 200, body }));
      const err = await caught(yt.listPlaylists(['PLfixtureAlpha01']));
      assert.equal(err.kind, 'malformed');
      assert.equal(err.scope, 'global');
      assert.equal(calls.length, 1);
    }
  });
});

describe('key redaction (U6)', () => {
  function assertNoKey(err: YouTubeError) {
    for (const text of [err.message, err.apiMessage ?? '', err.reason ?? '', err.url, String(err), err.stack ?? '', JSON.stringify(err)]) {
      assert.equal(text.includes(KEY), false, text);
    }
  }

  test('a network error that quotes the URL does not leak the key', async () => {
    const { yt } = client((url) => new Error(`request to ${url.href} failed, reason: socket hang up`));
    const err = await caught(yt.listPlaylists(['PLfixtureAlpha01']));
    assertNoKey(err);
    assert.match(err.apiMessage ?? '', /key=\[redacted\]/);
  });

  test('an API message that echoes the key does not leak it', async () => {
    const body = { error: { code: 400, message: `Bad key ${KEY} given`, errors: [{ reason: `odd-${KEY}` }] } };
    const { yt } = client(() => ({ status: 400, body }));
    const err = await caught(yt.listPlaylists(['PLfixtureAlpha01']));
    assertNoKey(err);
    assert.match(err.url, /key=\[redacted\]/);
  });

  test('redact leaves text alone when the key is empty', () => {
    assert.equal(redact('plain text', ''), 'plain text');
    assert.equal(redact('https://x.test/a?part=s&key=abc&id=1', ''), 'https://x.test/a?part=s&key=[redacted]&id=1');
  });
});

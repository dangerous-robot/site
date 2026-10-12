// Offline stand-in for the YouTube Data API, used by WATCH_DATA=fixture builds,
// browser tests and unit tests. It answers by URL path and query parameters,
// so the loader runs the same code path as a live build.
//
// The JSON is imported rather than read from disk: this module is bundled into
// the content config during astro build, where import.meta.url no longer
// points at src/lib/watch.
import type { FetchLike } from './youtube';
import playlistsBody from './fixtures/api/playlists.json';
import alphaPage1 from './fixtures/api/playlistItems-alpha-1.json';
import alphaPage2 from './fixtures/api/playlistItems-alpha-2.json';
import bravoItems from './fixtures/api/playlistItems-bravo.json';
import videosBody from './fixtures/api/videos.json';
import notFoundBody from './fixtures/api/error-playlist-not-found.json';
import quotaBody from './fixtures/api/error-quota.json';
import refererBody from './fixtures/api/error-referer-blocked.json';
import keyInvalidBody from './fixtures/api/error-key-invalid.json';

/** Every request fails with this error, to exercise the global error path. */
export type FixtureGlobalError = 'quota' | 'referer' | 'key-invalid';

const GLOBAL_ERRORS: Record<FixtureGlobalError, [number, unknown]> = {
  quota: [403, quotaBody],
  referer: [403, refererBody],
  'key-invalid': [400, keyInvalidBody],
};

const ALPHA_PAGE_2_TOKEN = alphaPage1.nextPageToken;

/** A fetch response with a JSON body; tests reuse it for their own fakes. */
export const reply = (status: number, body: unknown) => {
  const text = JSON.stringify(body);
  return Promise.resolve({ status, text: async () => text });
};

const badRequest = (message: string) => ({ error: { code: 400, message, errors: [{ reason: 'badRequest' }] } });

function idList(url: URL, name: string): string[] {
  return (url.searchParams.get(name) ?? '').split(',').filter(Boolean);
}

function playlistItems(url: URL): [number, unknown] {
  const pageToken = url.searchParams.get('pageToken');
  switch (url.searchParams.get('playlistId')) {
    case 'PLfixtureAlpha01':
      if (!pageToken) return [200, alphaPage1];
      if (pageToken === ALPHA_PAGE_2_TOKEN) return [200, alphaPage2];
      return [400, badRequest('Unknown fixture page token.')];
    case 'PLfixtureBravo02':
      return [200, bravoItems];
    default:
      // Charlie, and any ID the fixtures do not know.
      return [404, notFoundBody];
  }
}

export function createFixtureFetch(options: { globalError?: FixtureGlobalError } = {}): FetchLike {
  return (raw) => {
    if (options.globalError) return reply(...GLOBAL_ERRORS[options.globalError]);
    const url = new URL(raw);
    switch (url.pathname.replace(/^\/youtube\/v3\//, '')) {
      case 'playlists': {
        const ids = idList(url, 'id');
        return reply(200, { items: playlistsBody.items.filter((p) => ids.includes(p.id)) });
      }
      case 'playlistItems':
        return reply(...playlistItems(url));
      case 'videos': {
        // Deleted videos are simply absent, as from the real API.
        const ids = idList(url, 'id');
        return reply(200, { items: videosBody.items.filter((v) => ids.includes(v.id)) });
      }
      default:
        return reply(404, { error: { code: 404, message: 'Unknown fixture path.', errors: [{ reason: 'notFound' }] } });
    }
  };
}

export const fixtureFetch: FetchLike = createFixtureFetch();

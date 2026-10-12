// Resolves the /watch data mode from the build environment and
// builds the matching API client.
import type { WatchMode } from './types';
import { createYouTubeClient, type FetchLike, type YouTubeClient } from './youtube';

export interface WatchEnvironment {
  mode: WatchMode;
  /** The live key; null in fixture and none modes, so fixture builds never carry it. */
  key: string | null;
  /** WATCH_EXPECT_KEY=1: deploy builds warn when the key is missing. */
  expectKey: boolean;
  /** GITHUB_ACTIONS=true: warnings are also printed as workflow annotations. */
  githubActions: boolean;
}

/** Repo-relative curated list for each mode that fetches. */
export const CURATED_PATHS: Record<Exclude<WatchMode, 'none'>, string> = {
  live: 'src/content/watch/playlists.yaml',
  fixture: 'src/lib/watch/fixtures/playlists.fixture.yaml',
};

// fixtureFetch ignores the key; the client only needs a non-empty one.
const FIXTURE_KEY = 'fixture';

export function resolveMode(env: Record<string, string | undefined>): WatchEnvironment {
  // An empty or blank value, as an unset GitHub secret expands to, is no key.
  const key = env.YOUTUBE_API_KEY?.trim() || null;
  const base = { expectKey: env.WATCH_EXPECT_KEY === '1', githubActions: env.GITHUB_ACTIONS === 'true' };
  // Fixture wins over a key so fixture builds and browser tests stay offline
  // once a key is in .env.
  if (env.WATCH_DATA === 'fixture') return { ...base, mode: 'fixture', key: null };
  if (key) return { ...base, mode: 'live', key };
  return { ...base, mode: 'none', key: null };
}

/** The warning for a deploy build that has no key, else null. */
export function missingKeyWarning(env: Pick<WatchEnvironment, 'mode' | 'expectKey'>): string | null {
  return env.mode === 'none' && env.expectKey
    ? 'YOUTUBE_API_KEY is not set, so the watch page renders the empty state.'
    : null;
}

/** null in none mode. liveFetch is injectable for tests; builds use the global fetch. */
export async function createWatchClient(env: WatchEnvironment, liveFetch: FetchLike = globalThis.fetch): Promise<YouTubeClient | null> {
  if (env.mode === 'fixture') {
    // Imported only here so live builds do not bundle the fixture JSON.
    const { fixtureFetch } = await import('./fixtureFetch');
    return createYouTubeClient({ key: FIXTURE_KEY, fetch: fixtureFetch });
  }
  if (env.mode === 'live' && env.key) return createYouTubeClient({ key: env.key, fetch: liveFetch });
  return null;
}

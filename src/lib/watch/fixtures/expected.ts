// What a WATCH_DATA=fixture build of /watch must render. The fixture data is
// invented (playlists.fixture.yaml and api/), so the dist check and the
// browser specs read their expectations from here.
import type { PlaylistStatus } from '../types';

export interface FixturePlaylistExpectation {
  slug: string;
  youtubeId: string;
  status: PlaylistStatus;
  /** Video ids in playlist order. */
  videoIds: readonly string[];
}

/** Tab order on the page. */
export const FIXTURE_PLAYLISTS: readonly FixturePlaylistExpectation[] = [
  { slug: 'alpha', youtubeId: 'PLfixtureAlpha01', status: 'ok', videoIds: ['fxAlpha0001', 'fxAlpha0002', 'fxAlpha0003'] },
  { slug: 'bravo', youtubeId: 'PLfixtureBravo02', status: 'empty', videoIds: [] },
  { slug: 'charlie', youtubeId: 'PLfixtureCharlie3', status: 'failed', videoIds: [] },
];

/** Curated but missing from playlists.list, so never on the page. */
export const FIXTURE_OMITTED_SLUGS: readonly string[] = ['delta'];

export function fixturePlaylist(slug: string): FixturePlaylistExpectation {
  const found = FIXTURE_PLAYLISTS.find((p) => p.slug === slug);
  if (!found) throw new Error(`no fixture playlist ${slug}`);
  return found;
}

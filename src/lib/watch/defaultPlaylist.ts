// The playlist shown when the URL names none: the first playlist
// with videos, else the first. watch.astro renders it and parseUrl falls back
// to it, so both use this one rule or the page would swap panels on load.
import type { PlaylistStatus } from './types';

export function defaultPlaylist<T extends { status: PlaylistStatus }>(playlists: readonly T[]): T | undefined {
  return playlists.find((p) => p.status === 'ok') ?? playlists[0];
}

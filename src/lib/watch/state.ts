// URL state for /watch (UI spec § 4.8): ?list= is the curated slug and ?v=
// the YouTube video ID. Pure so arrival rules are unit tested; client/main.ts
// owns the live WatchState and calls history.replaceState.
import { defaultPlaylist } from './defaultPlaylist';
import type { PlaylistStatus, WatchState } from './types';

/** The least of the client data parseUrl needs, so tests can pass bare objects. */
export interface UrlPlaylist {
  slug: string;
  status: PlaylistStatus;
  videos: readonly { id: string }[];
}

function hasVideo(playlist: UrlPlaylist, id: string): boolean {
  return playlist.videos.some((v) => v.id === id);
}

function firstVideo(playlist: UrlPlaylist | undefined): WatchState['video'] {
  const first = playlist?.videos[0];
  return playlist && first ? { slug: playlist.slug, id: first.id } : null;
}

/**
 * Arrival state from location.search. Playlists are in tab order; with no
 * known list the tab is the server's default (defaultPlaylist). Only a known
 * v counts as loaded, so the rewritten URL (toSearch) keeps it and drops
 * anything unknown. video is null when the selected playlist has none.
 */
export function parseUrl(search: string, playlists: readonly UrlPlaylist[]): WatchState {
  const params = new URLSearchParams(search);
  const listParam = params.get('list');
  // An empty v counts as no v.
  const v = params.get('v') || null;
  const listed = listParam === null ? undefined : playlists.find((p) => p.slug === listParam);

  if (v !== null) {
    // An unknown list is ignored, so v falls back to the first playlist holding it.
    const owner = listed ?? playlists.find((p) => hasVideo(p, v));
    if (owner && hasVideo(owner, v)) {
      return { selectedSlug: owner.slug, video: { slug: owner.slug, id: v }, loaded: true, notice: false };
    }
  }

  const selected = listed ?? defaultPlaylist(playlists);
  return {
    selectedSlug: selected?.slug ?? '',
    video: firstVideo(selected),
    loaded: false,
    notice: v !== null,
  };
}

/** Before a video is loaded the URL follows the tab; after, it names the loaded video and stays put on tab changes. */
export function toSearch(state: WatchState): string {
  const params = new URLSearchParams();
  if (state.loaded && state.video) {
    params.set('list', state.video.slug);
    params.set('v', state.video.id);
  } else if (state.selectedSlug !== '') {
    params.set('list', state.selectedSlug);
  }
  const query = params.toString();
  return query === '' ? '' : `?${query}`;
}

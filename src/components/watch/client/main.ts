// Page controller for /watch. It alone owns WatchState, the URL, the panel
// shown and the live region; every other controller renders what the bus
// says and keeps no copy of the selection (plan § 4, "Startup and ownership").
import { ATTR, TESTID, emitWatch, onWatch } from '../../../lib/watch/contract';
import { parseUrl, toSearch } from '../../../lib/watch/state';
import type { WatchClientData, WatchControllerInit, WatchPlaylistView, WatchState } from '../../../lib/watch/types';
import { defaultPlaylist } from '../defaultPlaylist';
import { initGrid } from './grid';
import { initPlayer } from './player';
import { initPopup } from './popup';
import { initPreview } from './preview';
import { initTabs } from './tabs';

// Typed as the shared signature, so a controller that drifts from it fails
// the type check here.
const CONTROLLERS: WatchControllerInit[] = [initTabs, initPlayer, initGrid, initPopup, initPreview];

function readPlaylists(root: HTMLElement): WatchPlaylistView[] | null {
  const block = root.querySelector(`script[${ATTR.data}]`);
  if (!block?.textContent) return null;
  try {
    const data = JSON.parse(block.textContent) as WatchClientData;
    return Array.isArray(data.playlists) && data.playlists.length > 0 ? data.playlists : null;
  } catch {
    return null;
  }
}

/**
 * parseUrl falls back to the first playlist, but the server shows the first
 * one with videos; without this a URL with no list would swap panels on load.
 */
function arrivalState(search: string, playlists: WatchPlaylistView[]): WatchState {
  const state = parseUrl(search, playlists);
  const list = new URLSearchParams(search).get('list');
  if (state.loaded || playlists.some((p) => p.slug === list)) return state;
  const fallback = defaultPlaylist(playlists);
  if (!fallback) return state;
  const first = fallback.videos[0];
  return { ...state, selectedSlug: fallback.slug, video: first ? { slug: fallback.slug, id: first.id } : null };
}

function announcement(playlist: WatchPlaylistView): string {
  const n = playlist.videos.length;
  return n === 0 ? `${playlist.name}, no videos to show.` : `${playlist.name}, ${n} ${n === 1 ? 'video' : 'videos'}.`;
}

export function initWatch(): void {
  const root = document.querySelector<HTMLElement>(`[data-testid="${TESTID.page}"]`);
  // None mode renders no payload: there is nothing to control.
  const playlists = root ? readPlaylists(root) : null;
  if (!root || !playlists) return;

  const bySlug = new Map(playlists.map((p) => [p.slug, p]));
  const panels = [...root.querySelectorAll<HTMLElement>(`[data-testid="${TESTID.panel}"]`)];
  const status = root.querySelector<HTMLElement>(`[data-testid="${TESTID.status}"]`);
  const state = arrivalState(location.search, playlists);
  const bus = new EventTarget();
  let starting = true;

  const writeUrl = () => {
    // A bare replaceState('') would keep the old query, so the path is explicit.
    history.replaceState(history.state, '', `${location.pathname}${toSearch(state)}${location.hash}`);
  };

  for (const init of CONTROLLERS) init(root, bus, playlists);

  // Registered after the controllers, so a poster-follow watch:video emitted
  // here reaches them after they have rendered the tab change.
  onWatch(bus, 'watch:playlist', ({ slug }) => {
    const playlist = bySlug.get(slug);
    if (!playlist || (!starting && slug === state.selectedSlug)) return;
    state.selectedSlug = slug;
    for (const panel of panels) panel.hidden = panel.getAttribute(ATTR.playlist) !== slug;
    if (!starting) {
      if (status) status.textContent = announcement(playlist);
      // The poster follows the tab until something is loaded; an empty
      // playlist leaves the previous poster in place.
      const first = playlist.videos[0];
      if (!state.loaded && first) emitWatch(bus, 'watch:video', { slug, id: first.id, play: false, notice: false });
    }
    writeUrl();
  });

  onWatch(bus, 'watch:video', ({ slug, id, play, notice }) => {
    state.video = { slug, id };
    state.notice = notice;
    // Only ever set: a deep-linked video stays loaded when its poster is shown.
    if (play) state.loaded = true;
    writeUrl();
  });

  onWatch(bus, 'watch:play', ({ slug, id }) => {
    state.video = { slug, id };
    state.notice = false;
    state.loaded = true;
    writeUrl();
  });

  emitWatch(bus, 'watch:playlist', { slug: state.selectedSlug });
  if (state.video) emitWatch(bus, 'watch:video', { ...state.video, play: false, notice: state.notice });
  starting = false;
  writeUrl();
}

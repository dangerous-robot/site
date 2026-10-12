// Page controller for /watch. It alone owns WatchState, the URL, the panel
// shown and the live region; every other controller renders what the bus
// says and keeps no copy of the selection.
import { ATTR, TESTID, emitWatch, onWatch } from '../../../lib/watch/contract';
import { indexPlaylists } from '../../../lib/watch/index';
import { parseUrl, toSearch } from '../../../lib/watch/state';
import type { WatchClientData, WatchControllerInit, WatchPlaylistView } from '../../../lib/watch/types';
import { initGrid } from './grid';
import { initPlayer } from './player';
import { initPopup } from './popup';
import { initPreview } from './preview';
import { initTabs } from './tabs';
import { allByTestId, byTestId } from './dom';

// Typed as the shared signature, so a controller that drifts from it fails
// the type check here.
const CONTROLLERS: WatchControllerInit[] = [initTabs, initPlayer, initGrid, initPopup, initPreview];

/** Parses the payload once and removes its element; nothing else reads it. */
function takePlaylists(root: HTMLElement): WatchPlaylistView[] | null {
  const block = root.querySelector(`script[${ATTR.data}]`);
  if (!block?.textContent) return null;
  try {
    const data = JSON.parse(block.textContent) as WatchClientData;
    block.remove();
    return Array.isArray(data.playlists) && data.playlists.length > 0 ? data.playlists : null;
  } catch {
    return null;
  }
}

function announcement(playlist: WatchPlaylistView): string {
  const n = playlist.videos.length;
  return n === 0 ? `${playlist.name}, no videos to show.` : `${playlist.name}, ${n} ${n === 1 ? 'video' : 'videos'}.`;
}

export function initWatch(): void {
  const root = byTestId(document, TESTID.page);
  // None mode renders no payload: there is nothing to control.
  const playlists = root ? takePlaylists(root) : null;
  if (!root || !playlists) return;

  const index = indexPlaylists(playlists);
  const panels = allByTestId(root, TESTID.panel);
  const status = byTestId(root, TESTID.status);
  const state = parseUrl(location.search, playlists);
  const bus = new EventTarget();
  let starting = true;
  // A card pick keeps the poster from following the tab, as a loaded video
  // does, even while its embed still waits to go in.
  let picked = false;

  // One history write per action, however many state changes it makes.
  let urlQueued = false;
  const writeUrl = () => {
    if (urlQueued) return;
    urlQueued = true;
    queueMicrotask(() => {
      urlQueued = false;
      // A bare replaceState('') would keep the old query, so the path is explicit.
      history.replaceState(history.state, '', `${location.pathname}${toSearch(state)}${location.hash}`);
    });
  };

  for (const init of CONTROLLERS) init(root, bus, playlists);

  // Registered after the controllers, so a poster-follow watch:video emitted
  // here reaches them after they have rendered the tab change. tabs.ts emits
  // only for a tab that is not already selected.
  onWatch(bus, 'watch:playlist', ({ slug }) => {
    const playlist = index.bySlug(slug);
    if (!playlist) return;
    state.selectedSlug = slug;
    for (const panel of panels) panel.hidden = panel.getAttribute(ATTR.playlist) !== slug;
    if (!starting) {
      if (status) status.textContent = announcement(playlist);
      // The poster follows the tab until something is picked or loaded; an empty
      // playlist leaves the previous poster in place.
      const first = playlist.videos[0];
      if (!state.loaded && !picked && first) emitWatch(bus, 'watch:video', { slug, id: first.id, play: false, notice: false });
    }
    writeUrl();
  });

  // A pick does not load anything: the embed may wait on the half-in-view
  // gate, or never get it, so ?v= moves only on watch:play. Once a video is
  // loaded, the URL keeps naming it until another one starts.
  onWatch(bus, 'watch:video', ({ slug, id, play, notice }) => {
    if (play) picked = true;
    if (!state.loaded) state.video = { slug, id };
    state.notice = notice;
    writeUrl();
  });

  // loaded is never cleared: a deep-linked video stays loaded while only its poster shows.
  onWatch(bus, 'watch:play', ({ slug, id }) => {
    state.video = { slug, id };
    state.notice = false;
    state.loaded = true;
    writeUrl();
  });

  emitWatch(bus, 'watch:playlist', { slug: state.selectedSlug });
  if (state.video) {
    emitWatch(bus, 'watch:video', { ...state.video, play: false, notice: state.notice });
  } else {
    // Arrival on a playlist with no videos: no poster was ever set, so the
    // player hides (UI spec § 5), and an unknown v still gets its notice.
    const player = byTestId(root, TESTID.player);
    const notice = byTestId(root, TESTID.notice);
    if (player) player.hidden = true;
    if (notice) notice.hidden = !state.notice;
  }
  starting = false;
}

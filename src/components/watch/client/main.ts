// Page controller for /watch. It alone owns WatchState, the URL, the panel
// shown, each playlist's scroll position and the live region; every other
// controller renders what the bus says.
import { ATTR, TESTID, emitWatch, onWatch } from '../../../lib/watch/contract';
import { indexPlaylists } from '../../../lib/watch/index';
import { parseUrl, toSearch } from '../../../lib/watch/state';
import type { WatchClientData, WatchControllerInit, WatchPlaylistView } from '../../../lib/watch/types';
import { initList } from './list';
import { initPlayer } from './player';
import { initResizer } from './resizer';
import { initSwitcher } from './switcher';
import { allByTestId, byTestId } from './dom';

// Typed as the shared signature, so a controller that drifts from it fails
// the type check here.
const CONTROLLERS: WatchControllerInit[] = [initSwitcher, initPlayer, initList, initResizer];

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
  const lists = byTestId(root, TESTID.lists);
  const status = byTestId(root, TESTID.status);
  const state = parseUrl(location.search, playlists);
  const bus = new EventTarget();
  // One scroll box holds every panel, so each playlist's position is kept here.
  const scrollTops = new Map<string, number>();
  let starting = true;

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

  // Switching playlists never moves the player: the video in it stays
  // current, and the now-playing line offers the way back to it.
  onWatch(bus, 'watch:playlist', ({ slug }) => {
    const playlist = index.bySlug(slug);
    if (!playlist) return;
    if (lists && state.selectedSlug) scrollTops.set(state.selectedSlug, lists.scrollTop);
    state.selectedSlug = slug;
    for (const panel of panels) panel.hidden = panel.getAttribute(ATTR.playlist) !== slug;
    if (lists) lists.scrollTop = scrollTops.get(slug) ?? 0;
    if (!starting && status) status.textContent = announcement(playlist);
    writeUrl();
    // Only an empty player takes a poster from the playlist shown, as on
    // first load: after arriving on a playlist with no videos.
    const first = playlist.videos[0];
    if (!starting && !state.video && first) emitWatch(bus, 'watch:video', { slug, id: first.id, play: false, notice: false });
  });

  // A pick does not load anything: the embed may wait on the half-in-view
  // gate, or never get it, so ?v= moves only on watch:play. Once a video is
  // loaded, the URL keeps naming it until another one starts.
  onWatch(bus, 'watch:video', ({ slug, id, notice }) => {
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
    // Arrival on a playlist with no videos: there is no poster to show, so
    // the player hides, and an unknown v still gets its notice.
    const player = byTestId(root, TESTID.player);
    const notice = byTestId(root, TESTID.notice);
    if (player) player.hidden = true;
    if (notice) notice.hidden = !state.notice;
  }
  starting = false;
}

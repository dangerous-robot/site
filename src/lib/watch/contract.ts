// The /watch UI contract (plan § 4 and § Redesign). Components, client
// controllers, browser tests and the dist check all read these names, so a
// rename here is a rename everywhere. Nothing at module level may touch DOM
// globals: unit tests and the build import this file outside a browser.
import type { WatchEventDetailMap } from './types';

export const TESTID = {
  page: 'watch-page',
  /** The column holding the playlist switcher and the video lists. */
  listCol: 'watch-list-col',
  switcher: 'watch-switcher',
  /** "N of M" beside the Playlist label. */
  switcherPos: 'watch-switcher-pos',
  /** The current-playlist card that opens the menu. */
  trigger: 'watch-trigger',
  menu: 'watch-menu',
  /** One menu entry per playlist; the selected one is hidden. */
  option: 'watch-option',
  scrim: 'watch-scrim',
  /** The always-present "Now playing" / "Back to now playing" line. */
  nowPlaying: 'watch-now-playing',
  /** The scroll box holding every playlist's panel. */
  lists: 'watch-lists',
  panel: 'watch-panel',
  list: 'watch-list',
  thumb: 'watch-thumb',
  thumbTitle: 'watch-thumb-title',
  thumbDuration: 'watch-thumb-duration',
  resizer: 'watch-resizer',
  player: 'watch-player',
  playerFrame: 'watch-player-frame',
  play: 'watch-play',
  iframe: 'watch-iframe',
  playerTitle: 'watch-player-title',
  playerMeta: 'watch-player-meta',
  playerFrom: 'watch-player-from',
  youtubeLink: 'watch-youtube-link',
  notice: 'watch-notice',
  status: 'watch-status',
  /** Per-panel empty or failed state. */
  empty: 'watch-empty',
  /** Page-level empty state when there is no video data at all (none mode). */
  pageEmpty: 'watch-page-empty',
} as const;

export const ATTR = {
  /** On the watch-page root: live, fixture or none. */
  mode: 'data-watch-mode',
  /** Curated slug, on switcher cards, menu options, panel, thumb and player. */
  playlist: 'data-playlist',
  /** On thumb and player. */
  videoId: 'data-video-id',
  /** On the JSON payload script element. */
  data: 'data-watch-data',
} as const;

// Only the classes JS adds, creates or queries. Elements JS inserts are
// outside Astro's scoping, so their owners style them with :global().
export const CLASS = {
  thumbPlaying: 'watch-thumb__playing',
  playerIframe: 'watch-player__iframe',
  /** On a menu option whose playlist holds the video in the player. */
  optionPlaying: 'watch-option__playing',
} as const;

export const WATCH_EVENTS = {
  playlist: 'watch:playlist',
  video: 'watch:video',
  play: 'watch:play',
} as const satisfies Record<string, keyof WatchEventDetailMap>;

export type WatchEventName = keyof WatchEventDetailMap;

export function emitWatch<K extends WatchEventName>(bus: EventTarget, type: K, detail: WatchEventDetailMap[K]): void {
  bus.dispatchEvent(new CustomEvent(type, { detail }));
}

/** Returns a function that removes the listener. */
export function onWatch<K extends WatchEventName>(
  bus: EventTarget,
  type: K,
  handler: (detail: WatchEventDetailMap[K]) => void,
): () => void {
  const listener = (event: Event) => handler((event as CustomEvent<WatchEventDetailMap[K]>).detail);
  bus.addEventListener(type, listener);
  return () => bus.removeEventListener(type, listener);
}

export const EMBED_ORIGIN = 'https://www.youtube-nocookie.com';
export const EMBED_ALLOW = 'autoplay; encrypted-media; picture-in-picture; fullscreen';

// The iframe never gets a referrerpolicy attribute: YouTube answers a
// missing referrer with "Error 153".
export function embedUrl(videoId: string): string {
  return `${EMBED_ORIGIN}/embed/${encodeURIComponent(videoId)}?autoplay=1&rel=0`;
}

export function embedTitle(videoTitle: string): string {
  return `${videoTitle} (YouTube video)`;
}

/** YouTube rule: no autoplay until the player is more than half on screen. */
export const PLAYER_MIN_VISIBLE_RATIO = 0.5;

// CSS repeats this as a literal in media queries; keep both in step.
/** At this width and down the columns stack and the page scrolls. */
export const BREAKPOINT_STACK_PX = 860;

/** The video list column: default, drag limits and arrow-key steps (Shift for the big one). */
export const LIST_WIDTH = { initial: 380, min: 300, max: 560, step: 16, bigStep: 48 } as const;

export const YOUTUBE_TERMS_URL = 'https://www.youtube.com/t/terms';

export function youtubeWatchUrl(videoId: string, playlistYoutubeId: string): string {
  return `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}&list=${encodeURIComponent(playlistYoutubeId)}`;
}

export function youtubePlaylistUrl(playlistYoutubeId: string): string {
  return `https://www.youtube.com/playlist?list=${encodeURIComponent(playlistYoutubeId)}`;
}

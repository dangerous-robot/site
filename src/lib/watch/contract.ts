// The /watch UI contract (UI spec § 7 and § 8, plan § 4). Components, client
// controllers, browser tests and the dist check all read these names, so a
// rename here is a rename everywhere. Nothing at module level may touch DOM
// globals: unit tests and the build import this file outside a browser.
import type { WatchEventDetailMap } from './types';

export const TESTID = {
  page: 'watch-page',
  lede: 'watch-lede',
  tablist: 'watch-tablist',
  tab: 'watch-tab',
  panel: 'watch-panel',
  panelCount: 'watch-panel-count',
  grid: 'watch-grid',
  thumb: 'watch-thumb',
  thumbTitle: 'watch-thumb-title',
  thumbDuration: 'watch-thumb-duration',
  popup: 'watch-popup',
  player: 'watch-player',
  playerFrame: 'watch-player-frame',
  play: 'watch-play',
  iframe: 'watch-iframe',
  playerTitle: 'watch-player-title',
  playerMeta: 'watch-player-meta',
  youtubeLink: 'watch-youtube-link',
  backLink: 'watch-back-link',
  notice: 'watch-notice',
  previewSwitch: 'watch-preview-switch',
  previewHint: 'watch-preview-hint',
  status: 'watch-status',
  /** Per-panel empty or failed state. */
  empty: 'watch-empty',
  /** Page-level empty state when there is no video data at all (none mode). */
  pageEmpty: 'watch-page-empty',
} as const;

export const ATTR = {
  /** On the watch-page root: live, fixture or none. */
  mode: 'data-watch-mode',
  /** Curated slug, on tab, panel, thumb and player. */
  playlist: 'data-playlist',
  /** On thumb, player and popup. */
  videoId: 'data-video-id',
  /** sd or mq, on each thumb. */
  frameTier: 'data-frame-tier',
  /** "true" on a thumb while it cycles frames. */
  previewing: 'data-previewing',
  /** 1, 2 or 3 on a cycling thumb. */
  frame: 'data-frame',
  /** on or off, on the preview switch radios. */
  value: 'data-value',
  /** On the JSON payload script element. */
  data: 'data-watch-data',
} as const;

// Only the classes JS adds, creates or queries. Elements JS inserts are
// outside Astro's scoping, so their owners style them with :global().
export const CLASS = {
  thumbMedia: 'watch-thumb__media',
  thumbFrame: 'watch-thumb__frame',
  frameShown: 'is-shown',
  thumbPlaying: 'watch-thumb__playing',
  playerIframe: 'watch-player__iframe',
} as const;

/** Written only on an explicit choice, so an unset value can follow reduce-motion settings. */
export const PREVIEWS_STORAGE_KEY = 'dr-watch-previews';
export type PreviewsStoredValue = 'on' | 'off';

export const WATCH_EVENTS = {
  playlist: 'watch:playlist',
  video: 'watch:video',
  play: 'watch:play',
  preview: 'watch:preview',
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

// CSS repeats these as literals in media queries; keep both in step.
/** Rail beside the main column at this width and up. */
export const BREAKPOINT_DESKTOP_PX = 1120;
/** One grid column at this width and down. */
export const BREAKPOINT_PHONE_PX = 640;

/** Popups and previews are for mouse devices only. */
export const MQ_FINE_POINTER = '(hover: hover) and (pointer: fine)';
export const MQ_REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

export const YOUTUBE_TERMS_URL = 'https://www.youtube.com/t/terms';

export function youtubeWatchUrl(videoId: string, playlistYoutubeId: string): string {
  return `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}&list=${encodeURIComponent(playlistYoutubeId)}`;
}

export function youtubePlaylistUrl(playlistYoutubeId: string): string {
  return `https://www.youtube.com/playlist?list=${encodeURIComponent(playlistYoutubeId)}`;
}

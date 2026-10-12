// Shared data shapes for the /watch page. The loader stores WatchPlaylist;
// the page adds publishedText at build to make the view model the client
// reads. Wave 3 and 4 code imports these and must not redefine them.

export type WatchMode = 'live' | 'fixture' | 'none';
export type FrameTier = 'sd' | 'mq';
export type PlaylistStatus = 'ok' | 'empty' | 'failed';

export interface WatchCover {
  src: string;
  srcset: string;
}

export interface WatchVideo {
  id: string;
  title: string;
  channel: string;
  /** Both '' when the API duration cannot be parsed. */
  durationText: string;
  durationSpoken: string;
  publishedIso: string;
  /** Plain text, at most VIDEO_DESCRIPTION_MAX chars plus DESCRIPTION_ELLIPSIS. */
  description: string;
  cover: WatchCover;
  frameTier: FrameTier;
}

export interface WatchPlaylist {
  /** Curated slug from playlists.yaml; the ?list= value and the entry id. */
  slug: string;
  youtubeId: string;
  order: number;
  name: string;
  /** YAML creator, else the API channelTitle. */
  creator?: string;
  /** YAML description, else the API description cut at a word to PLAYLIST_DESCRIPTION_MAX. */
  description: string;
  status: PlaylistStatus;
  dataMode: Exclude<WatchMode, 'none'>;
  videos: WatchVideo[];
}

// publishedText comes from formatPostDate, which only runs at build time
// (src/lib/writing.ts imports astro:content), so the page adds it.
export type WatchVideoView = WatchVideo & { publishedText: string };
export type WatchPlaylistView = Omit<WatchPlaylist, 'videos'> & { videos: WatchVideoView[] };

export interface WatchBuildResult {
  mode: WatchMode;
  playlists: WatchPlaylist[];
  warnings: string[];
}

/** Owned by client/main.ts; controllers render bus events and keep no copy. */
export interface WatchState {
  /** Tab shown. */
  selectedSlug: string;
  /** Video in the player. */
  video: { slug: string; id: string } | null;
  /** A known deep-linked v, or an embed that has started (watch:play). */
  loaded: boolean;
  /** Unknown v on arrival. */
  notice: boolean;
}

/** Payload of the <script type="application/json" data-watch-data> block. */
export interface WatchClientData {
  playlists: WatchPlaylistView[];
}

// Bus event details, keyed by the WATCH_EVENTS names in contract.ts.
export interface WatchPlaylistEventDetail {
  slug: string;
}

/** play: false shows the poster only; only play: true marks a card playing. */
export interface WatchVideoEventDetail {
  slug: string;
  id: string;
  play: boolean;
  notice: boolean;
}

export interface WatchPlayEventDetail {
  slug: string;
  id: string;
}

export interface WatchPreviewEventDetail {
  enabled: boolean;
}

export interface WatchEventDetailMap {
  'watch:playlist': WatchPlaylistEventDetail;
  'watch:video': WatchVideoEventDetail;
  'watch:play': WatchPlayEventDetail;
  'watch:preview': WatchPreviewEventDetail;
}

/** Every src/components/watch/client/<name>.ts exports one of these as init<Name>. */
export type WatchControllerInit = (root: HTMLElement, bus: EventTarget, data: WatchPlaylistView[]) => void;

// Component props (UI spec § 3.3).
export interface WatchPlaylistTabsProps {
  playlists: WatchPlaylistView[];
  selectedSlug: string;
}

export interface WatchPlayerProps {
  video: WatchVideoView | null;
  playlist: WatchPlaylistView | null;
}

export interface WatchPanelProps {
  playlist: WatchPlaylistView;
  selected: boolean;
  eagerFirstRow: boolean;
}

export interface VideoThumbProps {
  video: WatchVideoView;
  playlist: WatchPlaylistView;
  eager: boolean;
}

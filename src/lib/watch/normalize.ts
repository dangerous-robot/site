// Turns YouTube API items into the WatchPlaylist the loader stores. Output is
// built to pass watchPlaylistSchema: a video that cannot be made valid is
// dropped and counted, never passed through with a placeholder.
import type { ApiPlaylist, ApiPlaylistItem, ApiThumbnailKey, ApiThumbnails, ApiVideo } from './youtube';
import type { WatchCover, WatchMode, WatchPlaylist, WatchVideo } from './types';
import type { CuratedPlaylist } from './schema';
import { DESCRIPTION_ELLIPSIS, PLAYLIST_DESCRIPTION_MAX, VIDEO_DESCRIPTION_MAX, VIDEO_ID_RE, watchVideoSchema } from './schema';
import { formatDuration, parseIsoDuration, spokenDuration } from './duration';
import { YTIMG_ORIGIN } from './frames';

export type DropReason =
  | 'missing'          // not returned by videos.list: deleted, private to the owner, or no video ID
  | 'duplicate'        // a later position of a video already kept
  | 'private'          // privacyStatus other than public or unlisted
  | 'not-processed'    // uploadStatus other than processed
  | 'live'             // live or upcoming broadcast
  | 'not-embeddable'
  | 'invalid';         // no usable title, ID, date or i.ytimg.com thumbnail, or fails watchVideoSchema

export type DropCounts = Partial<Record<DropReason, number>>;

export interface NormalizedPlaylist {
  playlist: WatchPlaylist;
  /** Total filtered out; videos past max_videos are not counted. */
  dropped: number;
  droppedBy: DropCounts;
}

/** Cuts plain text to max characters at a word, plus one ellipsis character. */
export function cutAtWord(text: string, max: number): string {
  const clean = text.replace(/\r\n?/g, '\n').trim();
  if (clean.length <= max) return clean;
  let cut = clean.slice(0, max);
  // When the next character is whitespace the slice already ends on a word.
  if (!/\s/.test(clean[max])) {
    const lastSpace = cut.search(/\s\S*$/);
    if (lastSpace > 0) cut = cut.slice(0, lastSpace);
  }
  cut = cut.trimEnd();
  // Never leave half of a surrogate pair (an emoji) before the ellipsis.
  const last = cut.charCodeAt(cut.length - 1);
  if (last >= 0xd800 && last <= 0xdbff) cut = cut.slice(0, -1);
  return cut + DESCRIPTION_ELLIPSIS;
}

// Nominal widths, used when the API leaves a width out. The order is the
// preference for the cover src: 480w is the card's largest common size.
const COVER_SIZES: [ApiThumbnailKey, number][] = [['high', 480], ['medium', 320], ['standard', 640], ['maxres', 1280]];
// Every image on the page comes from i.ytimg.com. No whitespace or comma,
// which would break the srcset list.
const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const YTIMG_RE = new RegExp(`^${escapeRegExp(YTIMG_ORIGIN)}/[^\\s,]+$`);

function usableUrl(thumbnails: ApiThumbnails | undefined, size: ApiThumbnailKey): string | null {
  const url = thumbnails?.[size]?.url;
  return typeof url === 'string' && YTIMG_RE.test(url) ? url : null;
}

/** Cover from medium, high, standard and maxres; null when none is on i.ytimg.com. */
export function coverFrom(thumbnails: ApiThumbnails | undefined): WatchCover | null {
  const found: { url: string; width: number }[] = [];
  for (const [size, nominal] of COVER_SIZES) {
    const url = usableUrl(thumbnails, size);
    if (!url) continue;
    const width = thumbnails?.[size]?.width;
    found.push({ url, width: Number.isInteger(width) && (width as number) > 0 ? (width as number) : nominal });
  }
  if (found.length === 0) return null;
  const src = found[0].url;
  const srcset = found
    .sort((a, b) => a.width - b.width)
    .filter((t, i, all) => i === 0 || t.width !== all[i - 1].width)
    .map((t) => `${t.url} ${t.width}w`)
    .join(', ');
  return { src, srcset };
}

function isoSeconds(text: string | undefined): string | null {
  const t = Date.parse(text ?? '');
  if (Number.isNaN(t)) return null;
  // Whole seconds with Z, the same shape the API sends.
  return new Date(t).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** One video, or null when it cannot be made valid. Filtering by status is separate. */
export function normalizeVideo(v: ApiVideo): WatchVideo | null {
  const id = v.id ?? '';
  const title = (v.snippet?.title ?? '').trim();
  const publishedIso = isoSeconds(v.snippet?.publishedAt);
  const cover = coverFrom(v.snippet?.thumbnails);
  if (!VIDEO_ID_RE.test(id) || !title || !publishedIso || !cover) return null;
  const seconds = parseIsoDuration(v.contentDetails?.duration ?? '');
  const video: WatchVideo = {
    id,
    title,
    channel: (v.snippet?.channelTitle ?? '').trim(),
    durationText: seconds === null ? '' : formatDuration(seconds),
    durationSpoken: seconds === null ? '' : spokenDuration(seconds),
    publishedIso,
    description: cutAtWord(v.snippet?.description ?? '', VIDEO_DESCRIPTION_MAX),
    cover,
    frameTier: usableUrl(v.snippet?.thumbnails, 'standard') ? 'sd' : 'mq',
  };
  // The same check the loader runs on the whole playlist, so one bad video
  // is dropped here rather than taking its playlist off the page.
  return watchVideoSchema.safeParse(video).success ? video : null;
}

function statusDrop(v: ApiVideo): DropReason | null {
  const privacy = v.status?.privacyStatus;
  if (privacy !== 'public' && privacy !== 'unlisted') return 'private';
  if (v.status?.uploadStatus !== 'processed') return 'not-processed';
  if (v.snippet?.liveBroadcastContent !== 'none') return 'live';
  if (v.status?.embeddable !== true) return 'not-embeddable';
  return null;
}

/** Playlist order, de-duplicated by first position, filtered, then capped at max. */
export function normalizeVideos(items: ApiPlaylistItem[], videos: ApiVideo[], max: number): { videos: WatchVideo[]; droppedBy: DropCounts } {
  const droppedBy: DropCounts = {};
  const drop = (reason: DropReason) => { droppedBy[reason] = (droppedBy[reason] ?? 0) + 1; };
  const byId = new Map(videos.filter((v) => v.id).map((v) => [v.id as string, v]));

  const ordered = items
    .map((item, index) => {
      const position = item.snippet?.position;
      return { item, position: typeof position === 'number' && Number.isFinite(position) ? position : index };
    })
    .sort((a, b) => a.position - b.position);

  const seen = new Set<string>();
  const kept: WatchVideo[] = [];
  for (const { item } of ordered) {
    const id = item.snippet?.resourceId?.videoId;
    if (id && seen.has(id)) { drop('duplicate'); continue; }
    if (id) seen.add(id);
    const api = id ? byId.get(id) : undefined;
    if (!api) { drop('missing'); continue; }
    const reason = statusDrop(api);
    if (reason) { drop(reason); continue; }
    // Past the cap, later items still count toward the status drops above.
    if (kept.length >= max) continue;
    const video = normalizeVideo(api);
    if (!video) { drop('invalid'); continue; }
    kept.push(video);
  }
  return { videos: kept, droppedBy };
}

function playlistFields(curated: CuratedPlaylist, api: ApiPlaylist, dataMode: Exclude<WatchMode, 'none'>) {
  const creator = curated.creator ?? (api.snippet?.channelTitle ?? '').trim();
  return {
    slug: curated.slug,
    youtubeId: curated.playlist_id,
    order: curated.order,
    name: (api.snippet?.title ?? '').trim(),
    // The schema rejects '', so an unknown creator is left out.
    ...(creator ? { creator } : {}),
    description: curated.description?.trim() || cutAtWord(api.snippet?.description ?? '', PLAYLIST_DESCRIPTION_MAX),
    dataMode,
  };
}

export function normalizePlaylist(input: {
  curated: CuratedPlaylist;
  api: ApiPlaylist;
  items: ApiPlaylistItem[];
  videos: ApiVideo[];
  dataMode: Exclude<WatchMode, 'none'>;
}): NormalizedPlaylist {
  const { videos, droppedBy } = normalizeVideos(input.items, input.videos, input.curated.max_videos);
  const dropped = Object.values(droppedBy).reduce((sum, n) => sum + n, 0);
  return {
    playlist: { ...playlistFields(input.curated, input.api, input.dataMode), status: videos.length > 0 ? 'ok' : 'empty', videos },
    dropped,
    droppedBy,
  };
}

/** Title known, videos not loadable this build. */
export function failedPlaylist(curated: CuratedPlaylist, api: ApiPlaylist, dataMode: Exclude<WatchMode, 'none'>): WatchPlaylist {
  return { ...playlistFields(curated, api, dataMode), status: 'failed', videos: [] };
}

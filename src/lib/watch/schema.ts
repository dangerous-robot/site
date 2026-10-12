// Schemas for the curated playlist list (src/content/watch/playlists.yaml)
// and for the normalized WatchPlaylist the loader stores. They live outside
// content.config.ts so unit tests can load them without Astro's loaders.
// Objects are strict so a stray or misspelled YAML key fails the build.
import { z } from 'astro/zod';
import type { WatchPlaylist } from './types';

export const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
export const PLAYLIST_ID_RE = /^PL[A-Za-z0-9_-]{11,32}$/;
export const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;

export const PLAYLIST_DESCRIPTION_MAX = 200;
export const VIDEO_DESCRIPTION_MAX = 500;
/** One character, so a cut description is at most its limit plus one. */
export const DESCRIPTION_ELLIPSIS = '…';

export const MAX_VIDEOS_DEFAULT = 50;
export const MAX_VIDEOS_LIMIT = 200;

const slug = z.string().regex(SLUG_RE, { message: 'slug must be kebab-case: lowercase letters, digits and single hyphens' });
const playlistId = z.string().regex(PLAYLIST_ID_RE, { message: 'playlist_id must look like a YouTube playlist ID (PL plus 11 to 32 characters)' });

export const curatedPlaylistSchema = z.strictObject({
  slug,
  playlist_id: playlistId,
  order: z.number().int().positive(),
  /** Editor copy; when absent the API description is used. */
  description: z.string().max(PLAYLIST_DESCRIPTION_MAX).optional(),
  /** Overrides the owner channel name from the API. */
  creator: z.string().min(1).optional(),
  max_videos: z.number().int().min(1).max(MAX_VIDEOS_LIMIT).default(MAX_VIDEOS_DEFAULT),
});

export type CuratedPlaylist = z.output<typeof curatedPlaylistSchema>;

function addDuplicateIssues<T>(
  items: T[],
  key: (item: T) => string | number,
  field: string,
  ctx: z.RefinementCtx,
): void {
  const seen = new Map<string | number, number>();
  items.forEach((item, index) => {
    const value = key(item);
    const first = seen.get(value);
    if (first === undefined) {
      seen.set(value, index);
      return;
    }
    ctx.addIssue({
      code: 'custom',
      path: ['playlists', index, field],
      message: `${field} ${JSON.stringify(value)} is already used by playlists[${first}]`,
    });
  });
}

export const curatedFileSchema = z.strictObject({
  playlists: z.array(curatedPlaylistSchema).min(1),
}).superRefine((data, ctx) => {
  addDuplicateIssues(data.playlists, (p) => p.slug, 'slug', ctx);
  addDuplicateIssues(data.playlists, (p) => p.playlist_id, 'playlist_id', ctx);
  addDuplicateIssues(data.playlists, (p) => p.order, 'order', ctx);
});

export type CuratedFile = z.output<typeof curatedFileSchema>;

export const watchVideoSchema = z.strictObject({
  id: z.string().regex(VIDEO_ID_RE, { message: 'video id must be 11 characters from A-Z, a-z, 0-9, _ and -' }),
  title: z.string().min(1),
  channel: z.string(),
  durationText: z.string(),
  durationSpoken: z.string(),
  publishedIso: z.iso.datetime(),
  description: z.string().max(VIDEO_DESCRIPTION_MAX + DESCRIPTION_ELLIPSIS.length),
  // D6: every image on the page comes from i.ytimg.com.
  cover: z.strictObject({
    src: z.string().startsWith('https://i.ytimg.com/'),
    srcset: z.string(),
  }),
  frameTier: z.enum(['sd', 'mq']),
});

export const watchPlaylistSchema = z.strictObject({
  slug,
  youtubeId: playlistId,
  order: z.number().int().positive(),
  name: z.string().min(1),
  creator: z.string().min(1).optional(),
  description: z.string().max(PLAYLIST_DESCRIPTION_MAX + DESCRIPTION_ELLIPSIS.length),
  status: z.enum(['ok', 'empty', 'failed']),
  dataMode: z.enum(['live', 'fixture']),
  videos: z.array(watchVideoSchema),
}).superRefine((data, ctx) => {
  // A status that disagrees with the video list is a loader bug; the page
  // would show a grid under an empty-state message or the reverse.
  if (data.status === 'ok' && data.videos.length === 0) {
    ctx.addIssue({ code: 'custom', path: ['videos'], message: 'status "ok" needs at least one video' });
  }
  if (data.status !== 'ok' && data.videos.length > 0) {
    ctx.addIssue({ code: 'custom', path: ['videos'], message: `status "${data.status}" must have no videos` });
  }
}) satisfies z.ZodType<WatchPlaylist>;

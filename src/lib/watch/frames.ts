// Image URLs for /watch cards (UI spec § 4.4). Every image on the
// page comes from i.ytimg.com. Frame URLs are undocumented, so the tier is
// picked at build from the API's thumbnails (sd only when `standard` exists)
// and the client still checks each frame (isPlaceholder).
import type { FrameTier, WatchCover } from './types';

/** schema.ts keeps its own copy because it is frozen; keep the two in step. */
export const YTIMG_ORIGIN = 'https://i.ytimg.com';

export const FRAME_COUNT = 3;

/** YouTube answers a missing frame with HTTP 404 and a 120x90 grey JPEG, which may not fire onerror. */
export const PLACEHOLDER_MAX_WIDTH = 120;

/** The tier's frames 1 to 3, in cycle order; the cover is not one of them. */
export function frameUrls(id: string, tier: FrameTier): string[] {
  const base = `${YTIMG_ORIGIN}/vi/${encodeURIComponent(id)}/${tier}`;
  return Array.from({ length: FRAME_COUNT }, (_, i) => `${base}${i + 1}.jpg`);
}

/** The loader builds and sorts srcset; an empty one becomes undefined so Astro drops the attribute. */
export function coverSrcset(cover: WatchCover): string | undefined {
  const srcset = cover.srcset.trim();
  return srcset === '' ? undefined : srcset;
}

export function isPlaceholder(naturalWidth: number): boolean {
  return naturalWidth <= PLACEHOLDER_MAX_WIDTH;
}

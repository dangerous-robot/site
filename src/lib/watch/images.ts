// Image URLs for /watch. Every image on the page comes from i.ytimg.com.
import type { WatchCover } from './types';

/** schema.ts keeps its own copy because it is frozen; keep the two in step. */
export const YTIMG_ORIGIN = 'https://i.ytimg.com';

/** The loader builds and sorts srcset; an empty one becomes undefined so Astro drops the attribute. */
export function coverSrcset(cover: WatchCover): string | undefined {
  const srcset = cover.srcset.trim();
  return srcset === '' ? undefined : srcset;
}

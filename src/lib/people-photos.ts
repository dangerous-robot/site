import type { ImageMetadata } from 'astro';

// Kept apart from reviewers.ts, which the reviewer check also loads under tsx,
// where import.meta.glob does not exist.
const PHOTOS = import.meta.glob<{ default: ImageMetadata }>(
  '../assets/people/*.{jpg,jpeg,png,webp,avif}',
  { eager: true },
);

/** The photo at src/assets/people/<handle>.<ext>, or null when there is none. */
export function profilePhoto(handle: string): ImageMetadata | null {
  for (const [path, mod] of Object.entries(PHOTOS)) {
    const base = path.split('/').pop()!.replace(/\.[^.]+$/, '');
    if (base === handle) return mod.default;
  }
  return null;
}

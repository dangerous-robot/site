import type { ImageMetadata } from 'astro';
import { getImage } from 'astro:assets';

/**
 * Base's share-image props for a post with an `image`: a 1200px JPEG (JPEG
 * because some share-card crawlers skip WebP and AVIF). No image: no props,
 * so Base keeps the default logo.
 */
export async function postShareImage(
  image: { src: ImageMetadata; alt: string } | undefined,
): Promise<{ ogImage?: string; ogImageAlt?: string }> {
  if (!image) return {};
  const { src } = await getImage({ src: image.src, width: 1200, format: 'jpeg' });
  return { ogImage: src, ogImageAlt: image.alt };
}

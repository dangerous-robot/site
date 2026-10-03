import { getCollection, type CollectionEntry } from 'astro:content';

export type Post = CollectionEntry<'writing'>;

export const WRITING_LEDE = 'Posts on avoiding AI, or using it wisely.';
export const WRITING_FEED_TITLE = 'Dangerous Robot: Writing';

const newestFirst = (posts: Post[]) => posts.sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());

/** Posts newest first. Drafts are visible in dev so authors can preview them, and dropped from production builds. */
export async function getPosts(): Promise<Post[]> {
  return newestFirst(await getCollection('writing', ({ data }) => !(import.meta.env.PROD && data.draft)));
}

/** Posts newest first, never drafts, even in dev: a feed reader can't tell a preview from a post. */
export async function getFeedPosts(): Promise<Post[]> {
  return newestFirst(await getCollection('writing', ({ data }) => !data.draft));
}

/** Frontmatter dates are date-only and parse as UTC midnight; formatting in UTC keeps them from shifting a day west of Greenwich. */
export function formatPostDate(date: Date): string {
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' });
}

export function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

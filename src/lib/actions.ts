import { getCollection, type CollectionEntry } from 'astro:content';

export type Action = CollectionEntry<'actions'>;

/** Actions newest first. Drafts are visible in dev so authors can preview them, and dropped from production builds. */
export async function getActions(): Promise<Action[]> {
  const actions = await getCollection('actions', ({ data }) => !(import.meta.env.PROD && data.draft));
  return actions.sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());
}

export const petitionHref = (action: Action) => `/petitions/${action.id}`;

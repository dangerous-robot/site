import { getCollection, type CollectionEntry } from 'astro:content';

export type Action = CollectionEntry<'actions'>;

/** Actions newest first. Drafts are visible in dev so authors can preview them, and dropped from production builds. */
export async function getActions(): Promise<Action[]> {
  const actions = await getCollection('actions', ({ data }) => !(import.meta.env.PROD && data.draft));
  return actions.sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());
}

/** The newest action with a spotlight line, for the homepage band; undefined hides the band. */
export async function getSpotlight(): Promise<Action | undefined> {
  return (await getActions()).find((a) => a.data.spotlight);
}

export const petitionHref = (action: Action) => `/petitions/${action.id}`;

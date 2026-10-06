import { getCollection } from 'astro:content';
import { getPosts } from './writing';
import { getActions, petitionHref } from './actions';

/** What the homepage spotlight band needs, whichever collection the entry came from. */
export interface Spotlight {
  label: string;
  href: string;
  title: string;
  description: string;
  pubDate: Date;
  petition?: { slug: string; statement?: string };
}

/**
 * The newest entry marked `featured` across writing, petitions and resources;
 * undefined hides the band. Drafts are already dropped from production by the
 * collection getters, so a featured draft only shows in dev.
 */
export async function getSpotlight(): Promise<Spotlight | undefined> {
  const [posts, actions, resources] = await Promise.all([
    getPosts(),
    getActions(),
    getCollection('resources'),
  ]);
  const candidates: Spotlight[] = [
    ...posts.filter((p) => p.data.featured).map((p) => ({
      label: 'Writing',
      href: `/writing/${p.id}`,
      title: p.data.title,
      description: p.data.description,
      pubDate: p.data.pubDate,
    })),
    ...actions.filter((a) => a.data.featured).map((a) => ({
      label: 'Petition',
      href: petitionHref(a),
      title: a.data.title,
      description: a.data.description,
      pubDate: a.data.pubDate,
      petition: { slug: a.data.petition, statement: a.data.petition_statement },
    })),
    ...resources.filter((r) => r.data.featured).map((r) => ({
      label: 'Resource',
      href: `/resources/${r.id}`,
      title: r.data.title,
      description: r.data.description,
      pubDate: r.data.pubDate,
    })),
  ];
  return candidates.sort((a, b) => b.pubDate.getTime() - a.pubDate.getTime())[0];
}

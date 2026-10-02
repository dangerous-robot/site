import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { getCollection } from 'astro:content';

export async function GET(context: APIContext) {
  // Unlike the pages, the feed never includes drafts, even in dev.
  const posts = (await getCollection('writing', ({ data }) => !data.draft))
    .sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());

  return rss({
    title: 'Dangerous Robot: Writing',
    description: 'Posts on avoiding AI, or using it wisely.',
    site: context.site!,
    // Matches trailingSlash: "never" in astro.config.ts.
    trailingSlash: false,
    xmlns: { atom: 'http://www.w3.org/2005/Atom' },
    customData: '<language>en-us</language><atom:link href="https://dangerousrobot.org/writing/rss.xml" rel="self" type="application/rss+xml"/>',
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      categories: post.data.tags,
      link: `/writing/${post.id}`,
    })),
  });
}

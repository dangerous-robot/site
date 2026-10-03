import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { getFeedPosts, WRITING_FEED_TITLE, WRITING_LEDE } from '../../lib/writing';

export async function GET(context: APIContext) {
  const posts = await getFeedPosts();
  const selfUrl = new URL('/writing/rss.xml', context.site).href;

  return rss({
    title: WRITING_FEED_TITLE,
    description: WRITING_LEDE,
    site: context.site!,
    // Matches trailingSlash: "never" in astro.config.ts.
    trailingSlash: false,
    xmlns: { atom: 'http://www.w3.org/2005/Atom' },
    customData: `<language>en-us</language><atom:link href="${selfUrl}" rel="self" type="application/rss+xml"/>`,
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      categories: post.data.tags,
      link: `/writing/${post.id}`,
    })),
  });
}

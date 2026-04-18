import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const sources = defineCollection({
  loader: glob({ pattern: '**/*.md', base: 'research/sources' }),
  schema: z.object({
    url: z.string().url(),
    archived_url: z.string().url().optional(),
    title: z.string(),
    publisher: z.string(),
    published_date: z.coerce.date().optional(),
    accessed_date: z.coerce.date(),
    kind: z.enum([
      'report',
      'article',
      'documentation',
      'dataset',
      'blog',
      'video',
      'index',
    ]),
    summary: z.string().max(200),
    key_quotes: z.array(z.string()).optional(),
  }),
});

const claims = defineCollection({
  loader: glob({ pattern: '**/*.md', base: 'research/claims' }),
  schema: z.object({
    entity: z.string(),
    category: z.enum([
      'ai-safety',
      'environmental-impact',
      'product-comparison',
      'consumer-guide',
      'ai-literacy',
      'data-privacy',
      'industry-analysis',
      'regulation-policy',
    ]),
    verdict: z.enum([
      'true',
      'mostly-true',
      'mixed',
      'mostly-false',
      'false',
      'unverified',
    ]),
    confidence: z.enum(['high', 'medium', 'low']),
    as_of: z.coerce.date(),
    sources: z.array(z.string()),
    review_cadence_days: z.number().default(60),
    next_review_due: z.coerce.date().optional(),
  }),
});

const entities = defineCollection({
  loader: glob({ pattern: '**/*.md', base: 'research/entities' }),
  schema: z.object({
    name: z.string(),
    type: z.enum(['company', 'product', 'topic']),
    website: z.string().url().optional(),
    aliases: z.array(z.string()).optional(),
    description: z.string(),
  }),
});

export const collections = { sources, claims, entities };

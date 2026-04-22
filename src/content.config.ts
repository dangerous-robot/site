import { defineCollection, z } from 'astro:content';
import { glob, file } from 'astro/loaders';
import yaml from 'js-yaml';

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
    title: z.string(),
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
    standard_slug: z.string().optional(),
    as_of: z.coerce.date(),
    sources: z.array(z.string()),
    recheck_cadence_days: z.number().default(60),
    next_recheck_due: z.coerce.date().optional(),
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

const standards = defineCollection({
  loader: file('research/templates.yaml', {
    parser: (text) => {
      const data = yaml.load(text) as { templates: unknown[] };
      return data.templates;
    },
  }),
  schema: z.object({
    slug: z.string(),
    text: z.string(),
    entity_type: z.enum(['company', 'product']),
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
    core: z.boolean().default(false),
    notes: z.string().optional(),
    vocabulary: z.record(z.string(), z.array(z.string())).optional(),
  }),
});

export const collections = { sources, claims, entities, standards };

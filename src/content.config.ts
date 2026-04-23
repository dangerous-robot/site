import { defineCollection, z } from 'astro:content';
import { glob, file } from 'astro/loaders';
import yaml from 'js-yaml';
import fs from 'node:fs/promises';
import nodePath from 'node:path';

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
    source_type: z.enum(['primary', 'secondary', 'tertiary']).optional(),
    summary: z.string().max(200),
    key_quotes: z.array(z.string()).optional(),
  }),
});

const auditSchema = z.object({
  schema_version: z.number(),
  pipeline_run: z.object({
    ran_at: z.coerce.date(),
    model: z.string(),
    agents: z.array(z.string()),
  }),
  sources_consulted: z.array(z.object({
    id: z.string(),
    url: z.string().url(),
    title: z.string(),
    ingested: z.boolean(),
  })),
  audit: z.object({
    analyst_verdict: z.string(),
    auditor_verdict: z.string(),
    analyst_confidence: z.string(),
    auditor_confidence: z.string(),
    verdict_agrees: z.boolean(),
    confidence_agrees: z.boolean(),
    needs_review: z.boolean(),
  }).nullable(),
  human_review: z.object({
    reviewed_at: z.coerce.date().nullable(),
    reviewer: z.string().nullable(),
    notes: z.string().nullable(),
    pr_url: z.string().url().nullable(),
  }),
});

/** Parse YAML frontmatter from a Markdown string. Returns { data, body }. */
function parseMarkdownFrontmatter(content: string): { data: Record<string, unknown>; body: string } {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!match) {
    return { data: {}, body: content };
  }
  const data = yaml.load(match[1]) as Record<string, unknown>;
  const body = match[2];
  return { data, body };
}

/** Recursively collect all .md files under a directory (Node 18+ compatible). */
async function walkMdFiles(dir: string, base: string = dir): Promise<string[]> {
  const results: string[] = [];
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = nodePath.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...await walkMdFiles(fullPath, base));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      results.push(nodePath.relative(base, fullPath));
    }
  }
  return results;
}

const claims = defineCollection({
  loader: {
    name: 'claims-with-audit',
    load: async ({ store, parseData, generateDigest, renderMarkdown }) => {
      store.clear();

      const claimsBase = nodePath.resolve('research/claims');
      const mdFiles = await walkMdFiles(claimsBase);

      for (const relPath of mdFiles) {
        const absPath = nodePath.join(claimsBase, relPath);

        // id: relative path without .md extension, e.g. "ecosia/renewable-energy-hosting"
        const id = relPath.replace(/\.md$/, '').replace(/\\/g, '/');

        const content = await fs.readFile(absPath, 'utf-8');
        const { data: frontmatter, body } = parseMarkdownFrontmatter(content);

        // Attempt to read paired sidecar
        const auditPath = absPath.replace(/\.md$/, '.audit.yaml');
        let parsedAudit: z.infer<typeof auditSchema> | undefined;

        try {
          const auditContent = await fs.readFile(auditPath, 'utf-8');
          parsedAudit = yaml.load(auditContent) as z.infer<typeof auditSchema>;
        } catch (err: unknown) {
          if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
            // No sidecar — expected for existing claims
            parsedAudit = undefined;
          } else {
            console.warn(`[claims loader] malformed sidecar: ${auditPath} — ${(err as Error).message}`);
            parsedAudit = undefined;
          }
        }

        const mergedData = {
          ...frontmatter,
          ...(parsedAudit !== undefined ? { audit: parsedAudit } : {}),
        };

        const parsed = await parseData({ id, data: mergedData });
        const digest = generateDigest(content + (parsedAudit ? JSON.stringify(parsedAudit) : ''));
        const rendered = await renderMarkdown(body);

        store.set({ id, data: parsed, body, filePath: nodePath.join('research/claims', relPath), digest, rendered });
      }
    },
  },
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
      'not-applicable',
    ]),
    confidence: z.enum(['high', 'medium', 'low']),
    criteria_slug: z.string().optional(),
    status: z.enum(['draft', 'published', 'archived']).default('draft'),
    as_of: z.coerce.date(),
    sources: z.array(z.string()),
    recheck_cadence_days: z.number().default(60),
    next_recheck_due: z.coerce.date().optional(),
    audit: auditSchema.optional(),
  }),
});

const entities = defineCollection({
  loader: glob({ pattern: '**/*.md', base: 'research/entities' }),
  schema: z.object({
    name: z.string(),
    type: z.enum(['company', 'product', 'topic', 'sector']),
    website: z.string().url().optional(),
    aliases: z.array(z.string()).optional(),
    description: z.string(),
  }),
});

const criteria = defineCollection({
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

export const collections = { sources, claims, entities, criteria };

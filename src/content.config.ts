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
      'paper',
    ]),
    source_type: z.enum(['primary', 'secondary', 'tertiary']).optional(),
    independence: z.enum(['first-party', 'independent', 'unknown']).optional(),
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
  // Per-agent model lineage. Optional during the v1 transition: existing sidecars
  // written before this field landed validate without it; new sidecars always carry it.
  models_used: z.record(z.string(), z.string()).optional(),
  sources_consulted: z.array(z.object({
    id: z.string(),
    url: z.string().url(),
    title: z.string(),
    ingested: z.boolean(),
    acquisition: z.object({
      stage: z.enum(['research', 'ingest']),
      origin: z.enum(['brave', 'tavily', 'arxiv', 's2', 'openalex', 'edgar']).optional(),
      recovered_via: z.enum(['archive_org']).optional(),
      outcome: z.enum(['matched', 'recovered']).optional(),
      query: z.string().optional(),
      paper_id: z.string().optional(),
      filing_accession: z.string().optional(),
    }).optional(),
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
    load: async ({ store, parseData, generateDigest, renderMarkdown, watcher }) => {
      store.clear();

      const claimsBase = nodePath.resolve('research/claims');

      watcher?.add(claimsBase);
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
    topics: z.array(z.enum([
      'ai-safety',
      'environmental-impact',
      'product-comparison',
      'consumer-guide',
      'ai-literacy',
      'data-privacy',
      'industry-analysis',
      'regulation-policy',
    ])).min(1).max(3),
    // Operational definitions for each verdict live in docs/architecture/glossary.md.
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
    // Source-pool diversity signal. Set by the analyst from `independence` + `kind`
    // on the claim's sources. See docs/architecture/source-quality.md.
    verification_level: z.enum([
      'claimed',
      'self-reported',
      'partially-verified',
      'independently-verified',
      'multiply-verified',
    ]).optional(),
    // One-sentence explanation when the confidence cap fires. Required reading
    // when `verification_level` is `claimed` or `self-reported`. See architecture doc.
    cap_rationale: z.string().max(400).optional(),
    // Per-claim overrides of source-level fields, used when a source classified
    // `independent` is actually restating a primary disclosure for this claim.
    // See docs/architecture/source-quality.md § Source overrides on claims.
    source_overrides: z.array(z.object({
      source: z.string(),
      independence: z.enum(['first-party', 'independent', 'unknown']).optional(),
      reason: z.string(),
    })).optional(),
    // One-sentence reader-facing takeaway rendered under the verdict badge on the
    // claim page. Optional during v1; the analyst pipeline doesn't yet generate it,
    // so operators add it by hand during review. Capped to keep it scannable.
    takeaway: z.string().max(200).optional(),
    // Short title for <title> tags (≤42 chars, leaving room for " - Dangerous Robot").
    // Falls back to `title` when absent. Useful when the research label exceeds SERP limits.
    seo_title: z.string().max(42).optional(),
    criteria_slug: z.string().optional(),
    status: z.enum(['draft', 'published', 'archived', 'blocked']).default('draft'),
    // Pipeline phase advanced by the Orchestrator while a claim is in
    // progress; absent on terminal states. See docs/plans/claim-lifecycle-states.md.
    phase: z.enum(['researching', 'ingesting', 'analyzing', 'evaluating']).optional(),
    // Set together with status='blocked' to record why the pipeline halted.
    blocked_reason: z.enum(['insufficient_sources', 'terminal_fetch_error', 'analyst_error']).optional(),
    as_of: z.coerce.date(),
    sources: z.array(z.string()),
    recheck_cadence_days: z.number().default(60),
    next_recheck_due: z.coerce.date().optional(),
    // Free-form operator-set tags. Behavioral tags are documented in AGENTS.md.
    tags: z.array(z.string()).default([]),
    audit: auditSchema.optional(),
  }),
});

const entities = defineCollection({
  loader: glob({ pattern: '**/*.md', base: 'research/entities' }),
  schema: z.object({
    name: z.string(),
    type: z.enum(['company', 'product', 'subject']),
    website: z.string().url().optional(),
    legal_name: z.string().min(1).optional(),
    verification_status: z.enum([
      'verified',
      'unverified-startup',
      'unverified-other',
    ]).optional(),
    aliases: z.array(z.string()).optional(),
    description: z.string(),
    founded: z.number().int().min(1800).max(new Date().getFullYear()).optional(),
    parent_company: z.string().regex(/^companies\/[a-z0-9-]+$/, {
      message: 'parent_company must be a slug ref of the form "companies/<slug>"',
    }).optional(),
    search_hints: z.object({
      include: z.array(z.string()).optional(),
      exclude: z.array(z.string()).optional(),
    }).optional(),
    sec_cik: z.string().regex(/^\d{10}$/, { message: 'sec_cik must be a 10-digit CIK' }).optional(),
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
    entity_type: z.enum(['company', 'product', 'subject']),
    topics: z.array(z.enum([
      'ai-safety',
      'environmental-impact',
      'product-comparison',
      'consumer-guide',
      'ai-literacy',
      'data-privacy',
      'industry-analysis',
      'regulation-policy',
    ])).min(1).max(3),
    core: z.boolean().default(false),
    notes: z.string().optional(),
    subjects: z.array(z.string().regex(/^subjects\/[a-z0-9-]+$/)).optional(),
    vocabulary: z.record(z.string(), z.array(z.string())).optional(),
  }).superRefine((data, ctx) => {
    const isSubject = data.entity_type === 'subject';
    const hasSubjects = !!data.subjects && data.subjects.length > 0;
    if (isSubject && !hasSubjects) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['subjects'],
        message: "subjects: required and non-empty when entity_type === 'subject'",
      });
    }
    if (!isSubject && hasSubjects) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['subjects'],
        message: "subjects: forbidden when entity_type !== 'subject'",
      });
    }
  }),
});

const matrixGroupKey = z.enum([
  'environmental',
  'models-safety',
  'privacy-data',
  'business',
  'product-access',
]);

const matrixCellType = z.enum([
  'yes',
  'no',
  'no-good',
  'partial',
  'planned',
  'text',
  'unknown',
  'na',
]);

const matrixCell = z.object({
  type: matrixCellType,
  detail: z.string().optional(),
  footnote: z.string().optional(),
});

const matrixSummary = z.object({
  ai_ethics: z.string().default(''),
  financial_transparency: z.string().default(''),
  environmental: z.string().default(''),
  notes: z.string().default(''),
});

const matrixProduct = z.object({
  key: z.string(),
  name: z.string(),
  url: z.string().url(),
  status: z.enum(['active', 'excluded']),
  excluded_reason: z.string().optional(),
  summary: matrixSummary.optional(),
});

const matrixFeature = z.object({
  key: z.string(),
  label: z.string(),
  group: matrixGroupKey,
  ideal: z.object({
    value: z.string(),
    note: z.string().optional(),
  }).optional(),
  cells: z.record(z.string(), matrixCell),
});

export const matrixDataSchema = z.object({
  lede: z.string().optional(),
  caption: z.string().optional(),
  groups: z.array(z.object({
    key: matrixGroupKey,
    label: z.string(),
  })),
  products: z.array(matrixProduct),
  features: z.array(matrixFeature),
  footnotes: z.array(z.object({
    subject: z.string(),
    text: z.string(),
  })).optional(),
}).superRefine((data, ctx) => {
  const groupKeys = new Set(data.groups.map((g) => g.key));
  data.features.forEach((feature, fIdx) => {
    if (!groupKeys.has(feature.group)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['features', fIdx, 'group'],
        message: `features[${fIdx}].group "${feature.group}" must reference an existing groups[].key`,
      });
    }
  });
  data.products.forEach((product, pIdx) => {
    if (product.status === 'excluded') {
      if (!product.excluded_reason || product.excluded_reason.trim() === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['products', pIdx, 'excluded_reason'],
          message: 'excluded_reason: required and non-empty when status === "excluded"',
        });
      }
    }
    if (product.status === 'active') {
      const summary = product.summary;
      const summaryFields = ['ai_ethics', 'financial_transparency', 'environmental', 'notes'] as const;
      if (!summary) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['products', pIdx, 'summary'],
          message: 'summary: required when status === "active"',
        });
      } else {
        for (const field of summaryFields) {
          if (!summary[field] || summary[field].trim() === '') {
            ctx.addIssue({
              code: z.ZodIssueCode.custom,
              path: ['products', pIdx, 'summary', field],
              message: `summary.${field}: required and non-empty when status === "active"`,
            });
          }
        }
      }
    }
  });
});

const resources = defineCollection({
  loader: glob({ pattern: '**/*.md', base: 'src/content/resources' }),
  schema: z.object({
    title: z.string(),
    description: z.string().max(200),
    pubDate: z.coerce.date(),
    layout: z.enum(['article', 'matrix', 'guide', 'tool']).default('article'),
    wallpaper: z.enum(['default', 'ai-safety', 'responsible-ai', 'none']).default('default'),
    topics: z.array(z.enum([
      'ai-literacy', 'ai-safety', 'consumer-guide', 'responsible-ai',
    ])).min(1).max(3),
    /** Layout-specific structured payload. Validated per-layout at render time. */
    data: z.unknown().optional(),
    noindex: z.boolean().default(false),
    /** External resources to surface with the entry on the hub page. */
    further_reading: z.array(z.object({
      title: z.string(),
      url: z.string().url(),
      publisher: z.string().optional(),
      last_checked: z.coerce.date().optional(),
    })).optional(),
  }),
});

export const collections = { sources, claims, entities, criteria, resources };

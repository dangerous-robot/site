// Schema for the Responsible AI matrix page's `data:` payload. Lives outside
// content.config.ts so unit tests can load it without Astro's loaders.
// Every object is strict: a misspelled evidence key must fail the build, not
// vanish and leave the cell "Not yet sourced".
import { z } from 'astro/zod';
import { isoDate } from './dates';

export const CLAIM_PATH_PREFIX = '/research/claims/';
export const SOURCE_PATH_PREFIX = '/research/sources/';

const matrixGroupKey = z.enum([
  'environmental',
  'models-safety',
  'privacy-data',
  'business',
  'product-access',
]);

export const matrixCellType = z.enum([
  'yes',
  'no',
  'partial',
  'text',
  'unknown',
  'na',
]);

const claimPath = z.string().regex(new RegExp(`^${CLAIM_PATH_PREFIX}[a-z0-9-]+/[a-z0-9-]+$`), {
  message: `claim must be a rendered path of the form "${CLAIM_PATH_PREFIX}<entity>/<slug>"`,
});

const sourcePath = z.string().regex(new RegExp(`^${SOURCE_PATH_PREFIX}\\d{4}/[a-z0-9-]+$`), {
  message: `source must be a rendered path of the form "${SOURCE_PATH_PREFIX}<yyyy>/<slug>"`,
});

const sourcePaths = z.array(sourcePath);

// A YAML date left unquoted parses as a Date; the page quotes its dates, but
// accept both and store the ISO day so every consumer reads a string.
const checkedDate = z.union([
  z.string().regex(/^\d{4}-\d{2}-\d{2}$/, { message: 'last_checked must be YYYY-MM-DD' }),
  z.date().transform(isoDate),
]);

const ownedBy = z.strictObject({
  name: z.string().min(1),
  kind: z.enum(['publicly-traded', 'conglomerate']),
  sources: sourcePaths.optional(),
});

export const matrixCell = z.strictObject({
  type: matrixCellType,
  detail: z.string().optional(),
  claim: claimPath.optional(),
  sources: sourcePaths.optional(),
  last_checked: checkedDate.optional(),
  /** Models row only: the models the cell names, each listed in the row's `large_models`. */
  models: z.array(z.string().min(1)).optional(),
  /** Ownership row only: one word from the `corporate-structure` vocabulary. */
  term: z.string().min(1).optional(),
  /** Ownership row only: the owner, when the company is owned by another. */
  owned_by: ownedBy.optional(),
});

const summaryEntry = z.union([
  z.string(),
  z.strictObject({
    text: z.string(),
    sources: sourcePaths.optional(),
    last_checked: checkedDate.optional(),
  }),
]);

export type SummaryEntry = z.infer<typeof summaryEntry>;

const matrixSummary = z.strictObject({
  ai_ethics: summaryEntry.default(''),
  financial_transparency: summaryEntry.default(''),
  environmental: summaryEntry.default(''),
  notes: summaryEntry.default(''),
});

export const SUMMARY_FIELDS = matrixSummary.keyof().options;
export type SummaryField = (typeof SUMMARY_FIELDS)[number];

export function summaryText(entry: SummaryEntry | undefined): string {
  if (entry === undefined) return '';
  return typeof entry === 'string' ? entry : entry.text;
}

const matrixProduct = z.strictObject({
  key: z.string(),
  name: z.string(),
  url: z.string().url(),
  status: z.enum(['active', 'excluded']),
  excluded_reason: z.string().optional(),
  initially_hidden: z.boolean().optional(),
  summary: matrixSummary.optional(),
  /** The research entity whose claims this product's cells may cite. */
  entity: z.string().regex(/^products\/[a-z0-9-]+$/, {
    message: 'entity must be a slug ref of the form "products/<slug>"',
  }).optional(),
  /** `source`: no claims may be cited for this product (TreadLightlyAI). */
  max_tier: z.literal('source').optional(),
});

const stanceCommon = {
  /** The one-sentence stance, shown in the Evidence section. */
  note: z.string().optional(),
  /** Why the attribute matters. */
  sources: sourcePaths.optional(),
  /** A Values position standing in for sources (Q11). */
  position: z.string().regex(/^\/values#[a-z0-9-]+$/).optional(),
};

const largeModels = z.strictObject({
  last_checked: checkedDate.optional(),
  sources: sourcePaths.optional(),
  large: z.array(z.string().min(1)),
  not_large: z.array(z.string().min(1)),
});

const stanceTerms = z.strictObject({
  good: z.array(z.string().min(1)),
  mixed: z.array(z.string().min(1)),
  bad: z.array(z.string().min(1)),
});

/** A stance row is one of three shapes; which one decides how its cells are judged. */
const matrixIdeal = z.union([
  /** Yes/no rows: the answer the page counts as responsible. */
  z.strictObject({ value: z.enum(['yes', 'no']), ...stanceCommon }),
  /** Models row: the short preferred answer and the dated large-model list. */
  z.strictObject({ answer: z.string().min(1), large_models: largeModels, ...stanceCommon }),
  /** Ownership row: the short preferred answer and the vocabulary split into good, mixed and bad. */
  z.strictObject({ answer: z.string().min(1), terms: stanceTerms, ...stanceCommon }),
]);

export const matrixFeature = z.strictObject({
  key: z.string(),
  label: z.string(),
  group: matrixGroupKey,
  /** The criteria slug every claim cited in this row must carry. */
  criterion: z.string().optional(),
  /** `inverted`: a True verdict means the answer is No (data used for training). */
  polarity: z.enum(['same', 'inverted']).default('same'),
  /** The only answers this row's cells may use. */
  answers: z.array(matrixCellType).optional(),
  ideal: matrixIdeal.optional(),
  cells: z.record(z.string(), matrixCell),
});

export const matrixDataSchema = z.strictObject({
  lede: z.string().optional(),
  caption: z.string().optional(),
  groups: z.array(z.strictObject({
    key: matrixGroupKey,
    label: z.string(),
  })),
  products: z.array(matrixProduct),
  features: z.array(matrixFeature),
  footnotes: z.array(z.strictObject({
    subject: z.string(),
    text: z.string(),
    sources: sourcePaths.optional(),
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
      if (!summary) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['products', pIdx, 'summary'],
          message: 'summary: required when status === "active"',
        });
      } else {
        for (const field of SUMMARY_FIELDS) {
          if (summaryText(summary[field]).trim() === '') {
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

export type MatrixData = z.infer<typeof matrixDataSchema>;
export type MatrixProduct = z.infer<typeof matrixProduct>;
export type MatrixFeature = z.infer<typeof matrixFeature>;
export type MatrixCell = z.infer<typeof matrixCell>;
export type MatrixCellType = z.infer<typeof matrixCellType>;
export type MatrixIdeal = z.infer<typeof matrixIdeal>;
export type OwnedBy = z.infer<typeof ownedBy>;
export type LargeModels = z.infer<typeof largeModels>;
export type StanceTerms = z.infer<typeof stanceTerms>;
export type MatrixFootnote = NonNullable<MatrixData['footnotes']>[number];

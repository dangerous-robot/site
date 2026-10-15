// Evidence tiers, stances and verdict agreement for the Responsible AI matrix.
// Plain types only (no astro:content), so the unit tests run under tsx.
// The rules are specified in docs/plans/completed/responsible-ai-chatbots-claims.md
// § Design.

import { isoDate } from './dates';
import {
  CLAIM_PATH_PREFIX,
  SOURCE_PATH_PREFIX,
  type LargeModels,
  type MatrixCell,
  type MatrixCellType,
  type MatrixFeature,
  type MatrixIdeal,
  type MatrixProduct,
  type OwnedBy,
  type StanceTerms,
  type SummaryField,
} from './matrixSchema';
import { findReviewer, type Person } from './reviewers';
import { CONFIDENCE_LABELS, type Confidence, type Verdict } from './verdict';

export type Answer = MatrixCellType;
export type Stance = 'good' | 'bad' | 'mixed' | 'neutral';
export type Tier = 'claim' | 'source' | 'none';
export type Polarity = MatrixFeature['polarity'];

export const TIER_NAMES: Record<Tier, string> = {
  claim: 'Reviewed claim',
  source: 'Source',
  none: 'Not yet sourced',
};

/** What a cell, summary entry or footnote cites. Any of them fits this shape. */
export interface Cited {
  claim?: string;
  sources?: string[];
  owned_by?: OwnedBy;
  last_checked?: string;
}

/** Who the evidence is about, for ids and link names. A feature row is one; so is a summary column. */
export type EvidenceSubject = Pick<MatrixFeature, 'key' | 'label'>;

/** The summary table's columns, in display order. */
export const SUMMARY_COLUMNS: { key: SummaryField; label: string }[] = [
  { key: 'ai_ethics', label: 'AI ethics' },
  { key: 'environmental', label: 'Environmental' },
  { key: 'financial_transparency', label: 'Financial transparency' },
  { key: 'notes', label: 'Notes' },
];

/** The subject a summary column's evidence belongs to; its key gives the `ev-summary-<field>-<product>` ids. */
export function summarySubject(column: { key: SummaryField; label: string }): EvidenceSubject {
  return { key: `summary-${column.key}`, label: `${column.label} summary` };
}

/** The product fields the evidence rules read. */
export type ProductRef = Pick<MatrixProduct, 'key' | 'name' | 'status' | 'entity' | 'max_tier'>;

export interface ClaimInfo {
  id: string;
  title: string;
  entity: string;
  status: 'draft' | 'published' | 'archived';
  verdict: Verdict;
  confidence: Confidence;
  as_of: Date;
  criteria_slug?: string;
  /** Raw reviewer value from the audit sidecar; null when unreviewed. */
  reviewer: string | null;
}

export interface SourceInfo {
  id: string;
  title: string;
  publisher: string;
  accessed_date: Date;
  archived_url?: string;
}

export interface EvidenceLookups {
  claims: Map<string, ClaimInfo>;
  sources: Map<string, SourceInfo>;
}


/** The collection id behind a rendered citation path, or null when the path has the wrong prefix. */
export function citedId(path: string, kind: 'claim' | 'source'): string | null {
  const prefix = kind === 'claim' ? CLAIM_PATH_PREFIX : SOURCE_PATH_PREFIX;
  if (!path.startsWith(prefix)) return null;
  const id = path.slice(prefix.length).replace(/\/$/, '');
  return id.length > 0 ? id : null;
}

/** The claim-page test: published, with a reviewer who maps to a person. `reviewed_at` alone is not enough. */
export function isReviewedClaim(claim: ClaimInfo | undefined): boolean {
  return claim?.status === 'published' && findReviewer(claim.reviewer) !== undefined;
}

export function isCapped(product: ProductRef): boolean {
  return product.max_tier === 'source';
}

export interface CellEvidence {
  tier: Tier;
  /**
   * The reviewed claim cited, if any, and the person who approved it. Present
   * below the "claim" tier too when an owner lowers the cell, so branch on
   * `tier`, not on `claim`.
   */
  claim?: ClaimInfo;
  reviewer?: Person;
  /** Every source path cited, the owner's included. */
  sourcePaths: string[];
}

/** The source behind a rendered citation path, when the lookups have it. */
export function sourceInfo(path: string, lookups: EvidenceLookups): SourceInfo | undefined {
  return lookups.sources.get(citedId(path, 'source') ?? '');
}

/**
 * What the citations amount to. A product capped at `max_tier: source` never
 * reaches "Reviewed claim". An ownership cell with an owner has two parts of
 * evidence and takes the lower tier: the owner's part is sources or nothing,
 * so the cell is "source" at best, and "none" if either part is bare.
 */
export function cellEvidence<T extends Cited>(cited: T, product: ProductRef, lookups: EvidenceLookups): CellEvidence {
  const ownSources = cited.sources ?? [];
  const ownerSources = cited.owned_by?.sources ?? [];
  const sourcePaths = [...ownSources, ...ownerSources];

  const claimId = cited.claim && !isCapped(product) ? citedId(cited.claim, 'claim') : null;
  const claim = claimId ? lookups.claims.get(claimId) : undefined;
  const reviewed = isReviewedClaim(claim);
  const ownTier: Tier = reviewed ? 'claim' : ownSources.length > 0 ? 'source' : 'none';
  const claimPart = reviewed ? { claim, reviewer: findReviewer(claim!.reviewer) } : {};

  if (!cited.owned_by) return { tier: ownTier, ...claimPart, sourcePaths };
  // The owner's part is sources or nothing, so the cell is "source" at best
  // and "none" if either part is bare; the claim stays visible either way.
  const tier: Tier = ownTier !== 'none' && ownerSources.length > 0 ? 'source' : 'none';
  return { tier, ...claimPart, sourcePaths };
}

export function cellTier<T extends Cited>(cited: T, product: ProductRef, lookups: EvidenceLookups): Tier {
  return cellEvidence(cited, product, lookups).tier;
}

/** The "Prefer" line under a stance row: an icon's answer (yes/no rows) or a few words (text rows). */
export function preferLine(ideal: MatrixIdeal | undefined): { value?: 'yes' | 'no'; word: string } | null {
  if (!ideal) return null;
  if ('value' in ideal) return { value: ideal.value, word: ideal.value === 'yes' ? 'Yes' : 'No' };
  return { word: ideal.answer };
}

export type RowKind = 'yes-no' | 'models' | 'ownership' | 'feature';

/** Which stance rule a row follows; a row with no `ideal` is a feature row. */
export function rowKind(feature: Pick<MatrixFeature, 'ideal'>): RowKind {
  const ideal = feature.ideal;
  if (!ideal) return 'feature';
  if ('value' in ideal) return 'yes-no';
  return 'large_models' in ideal ? 'models' : 'ownership';
}

function modelsStance(models: string[] | undefined, list: LargeModels): Stance {
  if (!models || models.length === 0) return 'neutral';
  if (models.some((m) => list.large.includes(m))) return 'bad';
  if (models.every((m) => list.not_large.includes(m))) return 'good';
  return 'neutral';
}

function ownershipStance(cell: MatrixCell, terms: StanceTerms): Stance {
  if (cell.owned_by) return 'bad';
  if (!cell.term) return 'neutral';
  if (terms.bad.includes(cell.term)) return 'bad';
  if (terms.good.includes(cell.term)) return 'good';
  if (terms.mixed.includes(cell.term)) return 'mixed';
  return 'neutral';
}

/**
 * Good, bad, mixed or neutral: the page's opinion of the cell's answer.
 * Feature rows (no `ideal`) are always neutral.
 */
export function cellStance(cell: MatrixCell, feature: Pick<MatrixFeature, 'ideal'>): Stance {
  const ideal = feature.ideal;
  if (!ideal) return 'neutral';
  if ('value' in ideal) {
    if (cell.type === 'partial') return 'mixed';
    if (cell.type === 'yes' || cell.type === 'no') return cell.type === ideal.value ? 'good' : 'bad';
    return 'neutral';
  }
  if ('large_models' in ideal) return modelsStance(cell.models, ideal.large_models);
  return ownershipStance(cell, ideal.terms);
}

const ALLOWED_ANSWERS: Record<Verdict, Answer[]> = {
  'true': ['yes'],
  'mostly-true': ['yes', 'partial'],
  'mixed': ['partial'],
  'mostly-false': ['no', 'partial'],
  'false': ['no'],
  'unverified': ['unknown'],
  'not-applicable': ['na'],
};

const INVERTED: Partial<Record<Answer, Answer>> = { yes: 'no', no: 'yes' };

/** Whether a cited claim's verdict allows the cell's hand-entered answer. */
export function verdictAgrees(verdict: Verdict, answer: Answer, polarity: Polarity = 'same'): boolean {
  const normalized = polarity === 'inverted' ? (INVERTED[answer] ?? answer) : answer;
  return ALLOWED_ANSWERS[verdict].includes(normalized);
}

export interface PopupLink {
  href: string;
  text: string;
  /** Visually hidden suffix naming the product and row, so each link is distinct out of context. */
  srText: string;
}

/** A popup exists only for marked cells ("Reviewed claim" or "Source"); "Not yet sourced" has no mark. */
export interface PopupContent {
  tier: Tier;
  tierName: string;
  /** "GreenPT, hosted on renewable energy": names the product and row in accessible names. */
  forWhom: string;
  /** Reviewed claim only; the component renders the badge from `verdict`. */
  verdict?: Verdict;
  confidence?: string;
  asOf?: string;
  /** Source only: first source's publisher and accessed date, plus "and N more". */
  sourceLine?: string;
  link?: PopupLink;
}

/**
 * Row label in running text: "Hosted on renewable energy" becomes "hosted
 * on renewable energy". A label that opens with an acronym ("AI ethics")
 * keeps it.
 */
export function lowerLabel(label: string): string {
  if (/^[A-Z]{2}/.test(label)) return label;
  return label.charAt(0).toLowerCase() + label.slice(1);
}

export function evidenceId(subjectKey: string, productKey: string): string {
  return `ev-${subjectKey}-${productKey}`;
}

/** The Evidence entry's line for a cell with no citations. */
export function checkRecordLine<T extends Cited>(cited: T): string {
  return cited.last_checked
    ? `Checked by Dangerous Robot, ${cited.last_checked}. ${TIER_NAMES.none}.`
    : `${TIER_NAMES.none}.`;
}

/** Everything a mark's popup shows, as data; the component renders it. */
export function popupContent<T extends Cited>(
  cited: T,
  product: ProductRef,
  subject: EvidenceSubject,
  lookups: EvidenceLookups,
): PopupContent {
  const { tier, claim, sourcePaths } = cellEvidence(cited, product, lookups);
  const forWhom = `${product.name}, ${lowerLabel(subject.label)}`;
  const content: PopupContent = { tier, tierName: TIER_NAMES[tier], forWhom };

  if (tier === 'claim' && claim) {
    content.verdict = claim.verdict;
    content.confidence = CONFIDENCE_LABELS[claim.confidence];
    content.asOf = isoDate(claim.as_of);
    content.link = { href: cited.claim!, text: 'Open claim page', srText: `for ${forWhom}` };
  } else if (tier === 'source') {
    const first = sourceInfo(sourcePaths[0], lookups);
    const more = sourcePaths.length - 1;
    const head = first ? `${first.publisher}, accessed ${isoDate(first.accessed_date)}` : sourcePaths[0];
    content.sourceLine = more > 0 ? `${head}, and ${more} more` : head;
    content.link = { href: `#${evidenceId(subject.key, product.key)}`, text: 'See sources below', srText: `for ${forWhom}` };
  }
  return content;
}

export interface MatrixDataLike {
  products: ProductRef[];
  features: MatrixFeature[];
}

/** How many cells sit at each tier, over every active product. For progress reports, not the page. */
export function tierCounts(data: MatrixDataLike, lookups: EvidenceLookups): Record<Tier, number> {
  const counts: Record<Tier, number> = { claim: 0, source: 0, none: 0 };
  const active = data.products.filter((p) => p.status === 'active');
  for (const feature of data.features) {
    for (const product of active) {
      const cell = feature.cells[product.key];
      if (cell) counts[cellTier(cell, product, lookups)]++;
    }
  }
  return counts;
}

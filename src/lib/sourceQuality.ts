// Plain-language gloss text for the verification scale.
// Mirrors docs/architecture/source-quality.md § Verification scale —
// edit both files together.

export type VerificationLevel =
  | 'claimed'
  | 'self-reported'
  | 'partially-verified'
  | 'independently-verified'
  | 'multiply-verified';

export type Independence = 'first-party' | 'independent' | 'unknown';

export const VERIFICATION_LEVEL_LABELS: Record<VerificationLevel, string> = {
  'claimed': 'Claimed',
  'self-reported': 'Self-reported',
  'partially-verified': 'Partially verified',
  'independently-verified': 'Independently verified',
  'multiply-verified': 'Cross-verified',
};

export const VERIFICATION_LEVEL_GLOSS: Record<VerificationLevel, string> = {
  'claimed': 'The entity asserts this; no formal documentation or independent source was found.',
  'self-reported': 'The entity has published formal documentation; no independent source was found to corroborate.',
  'partially-verified': 'A mix of entity documentation and independent sources.',
  'independently-verified': 'At least one independent source corroborates this claim.',
  'multiply-verified': 'Multiple independent sources corroborate this claim.',
};

export const CAPPED_VERIFICATION_LEVELS: ReadonlySet<VerificationLevel> = new Set([
  'claimed',
  'self-reported',
]);

export type SourceCounts = {
  total: number;
  firstParty: number;
  independent: number;
  unknown: number;
};

export type SourceLike = {
  data: { independence?: Independence };
};

export type ClaimSourceOverride = {
  source: string;
  independence?: Independence;
  reason: string;
};

/**
 * Count sources by effective independence, applying any per-claim source_overrides.
 *
 * Sources missing from the index (broken refs) are still counted toward `total`
 * but classified as `unknown` so the displayed N matches `claim.sources.length`.
 */
export function countSourcesByIndependence(
  sourceRefs: readonly string[],
  sourceById: Map<string, SourceLike>,
  overrides?: readonly ClaimSourceOverride[],
): SourceCounts {
  const overrideMap = new Map<string, Independence | undefined>(
    (overrides ?? []).map((o) => [o.source, o.independence]),
  );
  const counts: SourceCounts = { total: 0, firstParty: 0, independent: 0, unknown: 0 };
  for (const ref of sourceRefs) {
    counts.total += 1;
    const overridden = overrideMap.get(ref);
    const indep: Independence | undefined =
      overridden ?? sourceById.get(ref)?.data.independence ?? undefined;
    if (indep === 'first-party') counts.firstParty += 1;
    else if (indep === 'independent') counts.independent += 1;
    else counts.unknown += 1;
  }
  return counts;
}

export function formatSourceCounts(counts: SourceCounts): string {
  const noun = counts.total === 1 ? 'source' : 'sources';
  const parts: string[] = [];
  if (counts.firstParty > 0) parts.push(`${counts.firstParty} company-published`);
  if (counts.independent > 0) parts.push(`${counts.independent} independent`);
  if (counts.unknown > 0) parts.push(`${counts.unknown} unclassified`);
  if (parts.length === 0) return `${counts.total} ${noun}`;
  return `${counts.total} ${noun} (${parts.join(', ')})`;
}

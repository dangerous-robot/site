export type Verdict = 'true' | 'mostly-true' | 'mixed' | 'mostly-false' | 'false' | 'unverified' | 'not-applicable';

export const VERDICT_ORDER: Verdict[] = [
  'true', 'mostly-true', 'mixed', 'mostly-false', 'false', 'unverified', 'not-applicable',
];

export const VERDICT_LABELS: Record<Verdict, string> = {
  'true': 'True',
  'mostly-true': 'Mostly true',
  'mixed': 'Mixed',
  'mostly-false': 'Mostly false',
  'false': 'False',
  'unverified': 'Unverified',
  'not-applicable': 'N/A',
};

export const VERDICT_TOOLTIP: Record<Verdict, string> = {
  'true': 'Claim is accurate and well-supported',
  'mostly-true': 'Claim is largely accurate with minor caveats',
  'mixed': 'Claim has significant elements of both truth and falsehood',
  'mostly-false': 'Claim is largely inaccurate with some basis in fact',
  'false': 'Claim is inaccurate',
  'unverified': 'Insufficient evidence to assess this claim',
  'not-applicable': 'This criterion does not apply to this entity',
};

/** CSS class suffix matching --color-verdict-* tokens */
export const VERDICT_KIND: Record<Verdict, string> = {
  'true': 'true',
  'mostly-true': 'mostly-true',
  'mixed': 'mixed',
  'mostly-false': 'mostly-false',
  'false': 'false',
  'unverified': 'unverified',
  'not-applicable': 'not-applicable',
};

export const VERDICT_RATINGS: Record<Verdict, number> = {
  'true': 5,
  'mostly-true': 4,
  'mixed': 3,
  'mostly-false': 2,
  'false': 1,
  'unverified': 3,
  'not-applicable': 3,
};

export function sortByVerdict<T>(items: T[], getVerdict: (item: T) => Verdict): T[] {
  return [...items].sort((a, b) =>
    VERDICT_ORDER.indexOf(getVerdict(a)) - VERDICT_ORDER.indexOf(getVerdict(b))
  );
}

export function verdictCounts(verdicts: Verdict[]): Record<Verdict, number> {
  const counts = Object.fromEntries(VERDICT_ORDER.map(v => [v, 0])) as Record<Verdict, number>;
  for (const v of verdicts) counts[v]++;
  return counts;
}

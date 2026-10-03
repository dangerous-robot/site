export interface ReviewerDisplay {
  name: string;
  href: string;
}

// Audit sidecars store the reviewer as an email address. Readers see the name
// instead, so an address never reaches the rendered page. Keys are lowercase.
const REVIEWERS: Record<string, ReviewerDisplay> = {
  'brandon@dangerousrobot.org': { name: 'Brandon Faloona', href: '/about#who-runs-this' },
};

/**
 * Display info for a raw reviewer value, or null when the value is empty.
 * Throws on a value with no mapping, failing the build: a reviewed claim must
 * name the person who stands behind it. Callers must never print the raw value.
 */
export function resolveReviewer(raw: string | null | undefined, context: string): ReviewerDisplay | null {
  if (!raw) return null;
  const display = REVIEWERS[raw.trim().toLowerCase()];
  if (!display) {
    throw new Error(`${context}: reviewer has no entry in src/lib/reviewers.ts; add one before building`);
  }
  return display;
}

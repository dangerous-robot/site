export interface ReviewerDisplay {
  name: string;
  href: string;
}

// Audit sidecars store the reviewer as an email address. Readers see the name
// instead, so an address never reaches the rendered page. Keys are lowercase.
const REVIEWERS: Record<string, ReviewerDisplay> = {
  'brandon@dangerousrobot.org': { name: 'Brandon Faloona', href: '/about#who-runs-this' },
};

/** Display info for a raw reviewer value, or null when the value is empty or has no mapping. Callers must never print the raw value. */
export function resolveReviewer(raw: string | null | undefined): ReviewerDisplay | null {
  if (!raw) return null;
  return REVIEWERS[raw.trim().toLowerCase()] ?? null;
}

// Shared by PetitionSign.astro's build-time render and its browser script,
// so the no-JS text and the live text cannot drift apart. Keep this file free
// of astro:content imports: it ships to the browser.

/** Public JSON from GET /petitions/{slug} on the dr-api Worker. */
export interface PetitionState {
  status: 'open' | 'closed';
  closed_at: string | null;
  count: number;
  names: string[];
}

/** Same format as formatPostDate in src/lib/writing.ts. */
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' });
}

export function petitionSummary(s: PetitionState): string {
  const count = s.count === 0 ? 'no signatures' : `${s.count} ${s.count === 1 ? 'signatory' : 'signatories'}`;
  if (s.status === 'closed') return `Closed${s.closed_at ? ` on ${formatDate(s.closed_at)}` : ''}, ${count}.`;
  return `${count[0].toUpperCase()}${count.slice(1)}${s.count === 0 ? ' yet' : ''}.`;
}

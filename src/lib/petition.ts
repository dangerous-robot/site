// Shared by PetitionSign.astro's build-time render and its browser script,
// so the no-JS text and the live text cannot drift apart. Keep this file free
// of astro:content imports and Node-only APIs: it ships to the browser.

/** Public JSON from GET /petitions/{slug} on the dr-api Worker. */
export interface PetitionState {
  status: 'open' | 'closed';
  closed_at: string | null;
  count: number;
  names: string[];
}

export const PETITION_API: string = import.meta.env.PUBLIC_PETITION_API ?? 'https://api.dangerousrobot.org';

/**
 * Reads a petition from the Worker. Resolves null on any failure (Worker down,
 * row not created yet, timeout), so a page can build and render without it.
 */
export async function fetchPetitionState(slug: string): Promise<PetitionState | null> {
  try {
    const res = await fetch(`${PETITION_API}/petitions/${slug}`, { signal: AbortSignal.timeout(3000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

/** Same format as formatPostDate in src/lib/writing.ts. */
function formatClosedDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' });
}

/** "on March 3, 2027" beside the Closed chip; empty while open or undated. */
export function closedText(s: PetitionState): string {
  return s.status === 'closed' && s.closed_at ? `on ${formatClosedDate(s.closed_at)}` : '';
}

/** Thousands separators so a large tally reads at a glance. */
export function formatCount(count: number): string {
  return count.toLocaleString('en-US');
}

export function signatureWord(count: number): string {
  return count === 1 ? 'signature' : 'signatures';
}

export function statusLabel(s: PetitionState): string {
  return s.status === 'closed' ? 'Closed' : 'Open';
}

/** The homepage menu's one-line tally: "152 signed", or "Closed, 152 signed". */
export function petitionSummary(s: PetitionState): string {
  const signed = `${formatCount(s.count)} signed`;
  return s.status === 'closed' ? `Closed, ${signed}` : signed;
}

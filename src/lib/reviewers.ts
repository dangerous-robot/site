export interface Person {
  handle: string;
  fullName: string;
}

export interface ReviewerDisplay {
  person: Person;
  name: string;
  href: string;
}

export const PEOPLE: Person[] = [
  { handle: 'brandon-f', fullName: 'Brandon Faloona' },
];

export const OPERATOR_HANDLE = 'brandon-f';

// Audit sidecars store the reviewer as an email address. Readers see the
// handle linked to the profile instead, so an address never reaches the
// rendered page. Keys are lowercase; values are handles in PEOPLE.
const REVIEWER_HANDLES: Record<string, string> = {
  'brandon@dangerousrobot.org': 'brandon-f',
};

export function profileHref(person: Person): string {
  return `/people/${person.handle}`;
}

export function operator(): Person {
  const person = PEOPLE.find((p) => p.handle === OPERATOR_HANDLE);
  if (!person) throw new Error(`OPERATOR_HANDLE ${OPERATOR_HANDLE} has no entry in PEOPLE`);
  return person;
}

export function reviewerHandle(raw: string | null | undefined): string | null {
  if (!raw) return null;
  return REVIEWER_HANDLES[raw.trim().toLowerCase()] ?? null;
}

/**
 * Display info for a raw reviewer value, or null when the value is empty.
 * Throws on a value with no mapping, failing the build: a reviewed claim must
 * name the person who stands behind it. Callers must never print the raw value.
 */
export function resolveReviewer(raw: string | null | undefined, context: string): ReviewerDisplay | null {
  if (!raw) return null;
  const person = PEOPLE.find((p) => p.handle === reviewerHandle(raw));
  if (!person) {
    throw new Error(`${context}: reviewer has no entry in src/lib/reviewers.ts; add one before building`);
  }
  return { person, name: person.handle, href: profileHref(person) };
}

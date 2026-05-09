export const ENTITY_TYPE_PARENTS = {
  company: { label: "Companies", href: "/companies" },
  product: { label: "Products",  href: "/products"  },
  subject: { label: "Subjects",  href: "/subjects"  },
} as const;

export const ENTITY_TYPE_LABELS: Record<string, string> = {
  subject:   "Subject",
  company:   "Company",
  product:   "Product",
  claim:     "Claim",
  source:    "Source",
  criterion: "Criterion",
};

export type EntityType = keyof typeof ENTITY_TYPE_PARENTS;

export function getEntityParent(type: string) {
  return ENTITY_TYPE_PARENTS[type as keyof typeof ENTITY_TYPE_PARENTS] ?? null;
}

// Mirrors the Zod enum at src/content.config.ts and the verification_status
// branches in pipeline/orchestrator/persistence.py + pipeline/analyst/agent.py.
// Edit all three together.
export type VerificationStatus =
  | 'verified'
  | 'unverified-startup'
  | 'unverified-other';

export const VERIFICATION_STATUS_BADGE_TEXT: Record<VerificationStatus, string> = {
  'verified': '',
  'unverified-startup': 'Unverified — sparse public documentation (early-stage / startup)',
  'unverified-other': 'Unverified — limited public corroboration',
};

// JS mirror of resolve_parent_name in pipeline/orchestrator/entity_resolution.py
// (which calls slug.replace('-', ' ').title()). Used as a fallback label when
// a parent_company ref doesn't resolve to an existing entity in the collection.
export const titleCaseSlug = (slug: string): string =>
  slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

type EntityLike = { id: string; data: { name: string; type?: string; parent_company?: string } };

export function buildEntityMap<T extends EntityLike>(entities: readonly T[]): Map<string, T> {
  return new Map(entities.map(e => [e.id, e]));
}

export function resolveMadeBy<T extends EntityLike>(
  entity: T | null | undefined,
  entityMap: Map<string, T>,
): { href: string; label: string } | null {
  if (!entity || entity.data.type !== 'product') return null;
  const parentRef = entity.data.parent_company;
  if (!parentRef) return null;
  return {
    href: `/entities/${parentRef}`,
    label:
      entityMap.get(parentRef)?.data.name ??
      titleCaseSlug(parentRef.split('/').pop()!),
  };
}

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

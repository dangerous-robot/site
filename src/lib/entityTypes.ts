export const ENTITY_TYPE_PARENTS = {
  company: { label: "Companies", href: "/companies" },
  product: { label: "Products",  href: "/products"  },
  topic:   { label: "Topics",    href: "/topics"    },
  sector:  { label: "Sectors",   href: "/sectors"   },
} as const;

export type EntityType = keyof typeof ENTITY_TYPE_PARENTS;

export type Category =
  | 'ai-safety'
  | 'environmental-impact'
  | 'product-comparison'
  | 'consumer-guide'
  | 'ai-literacy'
  | 'data-privacy'
  | 'industry-analysis'
  | 'regulation-policy';

export const CATEGORY_LABELS: Record<Category, string> = {
  'ai-safety': 'AI Safety',
  'environmental-impact': 'Environmental Impact',
  'product-comparison': 'Product Comparison',
  'consumer-guide': 'Consumer Guide',
  'ai-literacy': 'AI Literacy',
  'data-privacy': 'Data Privacy',
  'industry-analysis': 'Industry Analysis',
  'regulation-policy': 'Regulation & Policy',
};

export const CATEGORIES: Category[] = Object.keys(CATEGORY_LABELS) as Category[];

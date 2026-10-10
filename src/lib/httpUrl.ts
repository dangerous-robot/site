import { z } from 'astro/zod';

/**
 * A URL that may become an href. Research frontmatter is LLM-written, and a
 * plain `.url()` accepts `javascript:` and `data:` schemes, so every URL field
 * that reaches the page goes through this instead.
 */
export const httpUrl = z.url({ protocol: /^https?$/, error: 'must be an http(s) URL' });

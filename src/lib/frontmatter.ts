import yaml from 'js-yaml';

/** Parse YAML frontmatter from a Markdown string. Returns { data, body }. */
export function parseMarkdownFrontmatter(content: string): { data: Record<string, unknown>; body: string } {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!match) {
    return { data: {}, body: content };
  }
  // An empty block loads as undefined.
  const data = (yaml.load(match[1]) ?? {}) as Record<string, unknown>;
  return { data, body: match[2] };
}

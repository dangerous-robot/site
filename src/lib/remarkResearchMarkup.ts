import { relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Remark plugin: research Markdown reaches the page as text and ordinary
 * links only.
 *
 * Files under `research/` are written by the pipeline's LLM agents from
 * third-party pages, so their text is data, never markup. Astro renders raw
 * HTML in Markdown by default, which would let a `<script>`, an `<img
 * onerror>` or a `[link](javascript:...)` in that text run on the live site.
 * This plugin drops raw HTML nodes and unwraps or drops links, images and
 * link definitions whose target is not http(s), mailto or relative.
 *
 * Other Markdown (`src/content/`) is written by people and keeps raw HTML.
 * A file whose path is unknown is treated as research, because the claims
 * loader renders through the loader API and "unknown" must fail safe.
 */

interface MdNode {
  type: string;
  url?: string;
  children?: MdNode[];
}

interface MdFile {
  path?: string;
}

const SAFE_SCHEMES = new Set(['http', 'https', 'mailto']);
// Anchored on this file, not the working directory, so a build started from
// another directory still recognizes research files.
const RESEARCH_DIR = fileURLToPath(new URL('../../research/', import.meta.url));

export function isResearchFile(file: MdFile): boolean {
  if (!file.path) return true;
  const rel = relative(RESEARCH_DIR, file.path);
  return rel !== '' && !rel.startsWith('..') && !rel.startsWith(sep);
}

/** True for relative targets, fragments, and http(s)/mailto. */
export function isSafeTarget(url: string): boolean {
  // Browsers ignore ASCII controls and whitespace inside a scheme, so a
  // "java<tab>script:" target would still run. Strip them before looking.
  const bare = Array.from(url).filter((c) => c.charCodeAt(0) > 0x20).join('');
  const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(bare);
  return scheme === null || SAFE_SCHEMES.has(scheme[1].toLowerCase());
}

function clean(parent: MdNode): void {
  const kept: MdNode[] = [];
  for (const node of parent.children ?? []) {
    if (node.type === 'html') continue;
    const target = node.url;
    const unsafe = target !== undefined && !isSafeTarget(target);
    if (unsafe && (node.type === 'image' || node.type === 'definition')) continue;
    if (node.children) clean(node);
    if (unsafe && node.type === 'link') {
      kept.push(...(node.children ?? []));
      continue;
    }
    kept.push(node);
  }
  parent.children = kept;
}

export default function remarkResearchMarkup() {
  return (tree: MdNode, file: MdFile): void => {
    if (isResearchFile(file)) clean(tree);
  };
}

// Node-only: reads the file system. Never import from browser code.
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseMarkdownFrontmatter } from './frontmatter';

export const FLYER_LINK_TEXT = 'print a flyer (PDF)';
export const FLYERS_DIR = 'public/flyers';
export const FLYER_TEMPLATE_FILES = ['src/pages/petitions/[slug]/flyer.astro', 'src/components/PetitionQr.astro', 'src/lib/qr.ts'];
export const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

// Here rather than in actions.ts, which imports astro:content and so cannot load
// in scripts; the page and the scripts share this one function.
export function petitionUrl(slug: string): string {
  if (!SLUG_RE.test(slug)) throw new Error(`petitionUrl: bad slug: ${slug}`);
  return `https://dangerousrobot.org/petitions/${slug}`;
}

export const flyerPdfPath = (slug: string): string => `/flyers/${slug}.pdf`;
export const flyerPagePath = (slug: string): string => `/petitions/${slug}/flyer`;

export interface FlyerManifest { slug: string; url: string; fingerprint: string; generated: string }
export interface PetitionAction { slug: string; draft: boolean; text: string }

/** Every action file whose front matter has a `petition` key, keyed by file name. */
export function listPetitionActions(actionsDir = 'src/content/actions'): PetitionAction[] {
  const out: PetitionAction[] = [];
  for (const file of readdirSync(actionsDir).filter((f) => f.endsWith('.md')).sort()) {
    const text = readFileSync(join(actionsDir, file), 'utf8');
    const { data } = parseMarkdownFrontmatter(text);
    if (typeof data !== 'object' || data === null || !Object.hasOwn(data, 'petition')) continue;
    const slug = file.slice(0, -'.md'.length);
    if (!SLUG_RE.test(slug)) throw new Error(`${file}: petition action file names must be lowercase kebab-case`);
    // Astro's glob loader would route the page under the slug key, not the file name.
    if (Object.hasOwn(data, 'slug')) throw new Error(`${file}: petition actions must not set a front matter slug`);
    out.push({ slug, draft: data.draft === true, text });
  }
  return out;
}

export function flyerFingerprint(text: string, url: string, templateFiles: string[] = FLYER_TEMPLATE_FILES): string {
  const templates = templateFiles.map((f) => (existsSync(f) ? readFileSync(f, 'utf8') : ''));
  return createHash('sha256').update([text, url, ...templates].join('\0')).digest('hex');
}

export function flyerState(slug: string, fingerprint: string, flyersDir = FLYERS_DIR): 'missing' | 'stale' | 'current' {
  const manifest = join(flyersDir, `${slug}.json`);
  if (!existsSync(join(flyersDir, `${slug}.pdf`)) || !existsSync(manifest)) return 'missing';
  const stored = JSON.parse(readFileSync(manifest, 'utf8')) as Partial<FlyerManifest>;
  return stored.fingerprint === fingerprint ? 'current' : 'stale';
}

export function writeFlyerManifest(manifest: FlyerManifest, flyersDir = FLYERS_DIR): void {
  writeFileSync(join(flyersDir, `${manifest.slug}.json`), JSON.stringify(manifest, null, 2) + '\n');
}

/** Page objects, not the /Pages tree. Chromium writes these object headers uncompressed. */
export function pdfPageCount(pdf: Buffer): number {
  return pdf.toString('latin1').match(/\/Type\s*\/Page(?![s\w])/g)?.length ?? 0;
}

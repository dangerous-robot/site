// Checks built HTML, so run after `astro build`. /watch matches its data mode,
// renders thumbnails that link to YouTube without any iframe before Play,
// carries the YouTube and Google policy links, and no API key reached dist/.
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { TESTID, ATTR, YOUTUBE_TERMS_URL } from '../src/lib/watch/contract';
import type { WatchMode, PlaylistStatus } from '../src/lib/watch/types';

// Override only to run the check against a scratch copy of the build.
const DIST = process.env.WATCH_CHECK_DIST ?? 'dist';
const DEPLOY = process.env.WATCH_CHECK_CONTEXT === 'deploy';
const WATCH_PAGE = join(DIST, 'watch', 'index.html');
const PRIVACY_PAGE = join(DIST, 'privacy', 'index.html');
const GOOGLE_PRIVACY_URL = 'https://policies.google.com/privacy';
const WATCH_URL_PREFIX = 'https://www.youtube.com/watch';
// Every Google API key starts with this prefix.
const KEY_PREFIX = 'AIza';

// The fixture data is invented, so its expected shape lives here with the check.
const FIXTURE_EXPECTED: { slug: string; status: PlaylistStatus; count: number }[] = [
  { slug: 'alpha', status: 'ok', count: 3 },
  { slug: 'bravo', status: 'empty', count: 0 },
  { slug: 'charlie', status: 'failed', count: 0 },
];

const errors: string[] = [];
const warnings: string[] = [];
const notes: string[] = [];

function allFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? allFiles(p) : [p];
  });
}

interface Tag { name: string; attrs: Map<string, string>; index: number }

// Quoted values may hold '>', so attributes are matched one by one.
const TAG_RE = /<([a-zA-Z][\w-]*)((?:\s+[^\s=>/"']+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>"']+))?)*)\s*\/?>/g;
const ATTR_RE = /([^\s=>/"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']+)))?/g;

function tags(html: string): Tag[] {
  return [...html.matchAll(TAG_RE)].map((m) => {
    const attrs = new Map<string, string>();
    for (const a of m[2].matchAll(ATTR_RE)) attrs.set(a[1].toLowerCase(), a[2] ?? a[3] ?? a[4] ?? '');
    return { name: m[1].toLowerCase(), attrs, index: m.index };
  });
}

const byTestId = (all: Tag[], id: string) => all.filter((t) => t.attrs.get('data-testid') === id);
const hasLink = (html: string, href: string) => tags(html).some((t) => t.name === 'a' && t.attrs.get('href') === href);

// B2: key leaks. Bytes, not text, so binary assets are covered too. Messages
// carry paths only, never the key or the text around a match.
const files = allFiles(DIST);
if (files.length === 0) errors.push(`B2: no files in ${DIST}/; run \`npm run build\` first`);
const key = process.env.YOUTUBE_API_KEY?.trim() ?? '';
for (const file of files) {
  const buf = readFileSync(file);
  if (buf.includes(KEY_PREFIX)) errors.push(`B2: ${file} contains "${KEY_PREFIX}"`);
  if (key && buf.includes(key)) errors.push(`B2: ${file} contains the value of YOUTUBE_API_KEY`);
}

// B5, the half that does not depend on /watch data.
if (!existsSync(PRIVACY_PAGE)) errors.push(`B5: missing ${PRIVACY_PAGE}`);
else if (!hasLink(readFileSync(PRIVACY_PAGE, 'utf8'), GOOGLE_PRIVACY_URL)) errors.push(`B5: ${PRIVACY_PAGE} does not link ${GOOGLE_PRIVACY_URL}`);

let mode: WatchMode | undefined;
let thumbCount = 0;

if (!existsSync(WATCH_PAGE)) {
  errors.push(`B1: missing ${WATCH_PAGE}; run \`npm run build\` first`);
} else {
  const raw = readFileSync(WATCH_PAGE, 'utf8');
  // The client bundle is inlined into the page and holds template strings such
  // as data-testid="${...}" and the iframe it creates on Play, so markup checks
  // ignore every script body.
  const html = raw.replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, '');
  const all = tags(html);

  const roots = byTestId(all, TESTID.page);
  const modeValue = roots[0]?.attrs.get(ATTR.mode);
  if (roots.length !== 1) errors.push(`B1: expected one ${TESTID.page} element, found ${roots.length}`);
  else if (modeValue === 'live' || modeValue === 'fixture' || modeValue === 'none') mode = modeValue;
  else errors.push(`B1: ${TESTID.page} has ${ATTR.mode}="${modeValue ?? ''}", expected live, fixture or none`);

  if (DEPLOY && mode === 'fixture') errors.push('deploy: /watch was built from fixture data (WATCH_DATA=fixture); fixture data must never ship');

  // B3: the player inserts its iframe only after Play.
  if (/<iframe\b/i.test(html)) errors.push(`B3: ${WATCH_PAGE} has an <iframe> outside script bodies`);

  const thumbs = byTestId(all, TESTID.thumb);
  thumbCount = thumbs.length;

  if (mode === 'none') {
    // B4, none mode: one page-level empty state and no video markup.
    if (byTestId(all, TESTID.pageEmpty).length !== 1) errors.push(`B4: none mode without exactly one ${TESTID.pageEmpty}`);
    if (thumbs.length > 0) errors.push(`B4: none mode, but ${thumbs.length} ${TESTID.thumb} elements`);
    notes.push('skipped: no video data');
  } else if (mode) {
    // B4: thumbnails are plain links to YouTube, so they work without JavaScript.
    if (thumbs.length === 0) errors.push(`B4: ${mode} mode, but no ${TESTID.thumb} elements`);
    for (const t of thumbs) {
      const href = t.attrs.get('href') ?? '';
      if (t.name !== 'a' || !href.startsWith(WATCH_URL_PREFIX)) {
        errors.push(`B4: ${TESTID.thumb} for video ${t.attrs.get(ATTR.videoId) ?? '?'} is <${t.name} href="${href}">, expected <a href="${WATCH_URL_PREFIX}...">`);
      }
    }

    // B5: YouTube API Services terms require the attribution link.
    if (!hasLink(html, YOUTUBE_TERMS_URL)) errors.push(`B5: ${WATCH_PAGE} does not link ${YOUTUBE_TERMS_URL}`);

    // B6: read each playlist's status and count from its rendered panel.
    const tabSlugs = byTestId(all, TESTID.tab).map((t) => t.attrs.get(ATTR.playlist) ?? '');
    const panels = byTestId(all, TESTID.panel);
    const rendered = panels.map((panel, i) => {
      const segment = html.slice(panel.index, panels[i + 1]?.index ?? html.length);
      const seg = tags(segment);
      const count = byTestId(seg, TESTID.thumb).length;
      const hasGrid = byTestId(seg, TESTID.grid).length > 0;
      const hasEmpty = byTestId(seg, TESTID.empty).length > 0;
      const status: PlaylistStatus | 'unknown' =
        hasGrid && !hasEmpty ? 'ok'
        : hasEmpty && !hasGrid ? (seg.some((t) => t.name === 'a' && (t.attrs.get('href') ?? '').startsWith('https://www.youtube.com/playlist')) ? 'failed' : 'empty')
        : 'unknown';
      return { slug: panel.attrs.get(ATTR.playlist) ?? '', status, count };
    });

    const panelSlugs = rendered.map((r) => r.slug);
    if (panelSlugs.join() !== tabSlugs.join()) errors.push(`B6: tabs [${tabSlugs.join(', ')}] do not match panels [${panelSlugs.join(', ')}]`);
    const outside = thumbs.length - rendered.reduce((n, r) => n + r.count, 0);
    if (outside > 0) errors.push(`B6: ${outside} ${TESTID.thumb} elements sit outside any ${TESTID.panel}`);
    for (const r of rendered) if (r.status === 'unknown') errors.push(`B6: panel ${r.slug} has neither a ${TESTID.grid} nor a ${TESTID.empty}, or both`);

    if (mode === 'fixture') {
      const want = FIXTURE_EXPECTED.map((e) => e.slug);
      if (tabSlugs.join() !== want.join()) errors.push(`B6: fixture tabs are [${tabSlugs.join(', ')}], expected [${want.join(', ')}]`);
      for (const e of FIXTURE_EXPECTED) {
        const r = rendered.find((x) => x.slug === e.slug);
        if (r && (r.status !== e.status || r.count !== e.count)) {
          errors.push(`B6: fixture panel ${e.slug} is ${r.status} with ${r.count} thumbs, expected ${e.status} with ${e.count}`);
        }
      }
    } else {
      // A single playlist failing must not block a deploy; it shows its own empty state.
      for (const r of rendered) if (r.status === 'empty' || r.status === 'failed') warnings.push(`watch playlist ${r.slug} is ${r.status}`);
    }
  }
}

for (const w of warnings) console.log(`::warning::${w}`);
for (const n of notes) console.log(n);
if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}
console.log(`check-watch-page: mode=${mode} thumbs=${thumbCount} files scanned=${files.length} ok`);

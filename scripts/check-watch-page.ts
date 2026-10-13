// Checks built HTML, so run after `astro build`. /watch matches its data mode,
// renders thumbnails that link to YouTube without any iframe before Play,
// /privacy carries the YouTube and Google policy links, and no API key
// reached dist/.
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { loadEnv } from 'vite';
import { TESTID, ATTR, YOUTUBE_TERMS_URL, youtubePlaylistUrl, youtubeWatchUrl } from '../src/lib/watch/contract';
import { FIXTURE_PLAYLISTS } from '../src/lib/watch/fixtures/expected';
import type { WatchMode, PlaylistStatus } from '../src/lib/watch/types';

// Override only to run the check against a scratch copy of the build.
const DIST = process.env.WATCH_CHECK_DIST ?? 'dist';
const DEPLOY = process.env.WATCH_CHECK_CONTEXT === 'deploy';
const WATCH_PAGE = join(DIST, 'watch', 'index.html');
const PRIVACY_PAGE = join(DIST, 'privacy', 'index.html');
const GOOGLE_PRIVACY_URL = 'https://policies.google.com/privacy';
// Every link the page builds starts with these; the IDs go after them.
const WATCH_URL_PREFIX = youtubeWatchUrl('', '').split('?')[0];
const PLAYLIST_URL_PREFIX = youtubePlaylistUrl('').split('?')[0];
// Every Google API key starts with this prefix.
const KEY_PREFIX = 'AIza';

const errors: string[] = [];
const warnings: string[] = [];
let note: string | undefined;

function allFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const p = join(dir, entry.name);
    return entry.isDirectory() ? allFiles(p) : [p];
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
const hasLink = (all: Tag[], href: string) => all.some((t) => t.name === 'a' && t.attrs.get('href') === href);
const linksTo = (all: Tag[], prefix: string) => all.some((t) => t.name === 'a' && (t.attrs.get('href') ?? '').startsWith(prefix));

// Key leaks. Bytes, not text, so binary assets are covered too. Messages
// carry paths only, never the key or the text around a match. The two pages
// checked below keep their buffers, so they are read once.
const files = allFiles(DIST);
if (files.length === 0) errors.push(`no files in ${DIST}/; run \`npm run build\` first`);
const contents = new Map<string, Buffer>();
// tsx does not load .env, so without this a local run never checks the exact
// key. The prefix keeps every other .env value out of this process, as in
// content.config.ts; a key set in the environment (CI) wins.
const key = (process.env.YOUTUBE_API_KEY ?? loadEnv('production', process.cwd(), 'YOUTUBE_API_KEY').YOUTUBE_API_KEY ?? '').trim();
for (const file of files) {
  const buf = readFileSync(file);
  if (file === WATCH_PAGE || file === PRIVACY_PAGE) contents.set(file, buf);
  if (key && buf.includes(key)) {
    errors.push(`key leak: ${file} contains the value of YOUTUBE_API_KEY`);
  } else if (buf.includes(KEY_PREFIX)) {
    // /watch holds YouTube titles and descriptions, where a creator may have
    // pasted a URL with someone's key in it. Failing on that would stop every
    // deploy and the weekly data refresh, so there it is only a warning.
    if (file === WATCH_PAGE) warnings.push(`key prefix: ${file} contains "${KEY_PREFIX}" (likely YouTube text, not this site's key)`);
    else errors.push(`key leak: ${file} contains "${KEY_PREFIX}"`);
  }
}
const readPage = (file: string) => contents.get(file)?.toString('utf8');

// YouTube API Services terms: the site's own terms (here, /privacy) must
// link the YouTube Terms of Service and the Google Privacy Policy.
const privacy = readPage(PRIVACY_PAGE);
if (privacy === undefined) errors.push(`privacy link: missing ${PRIVACY_PAGE}`);
else {
  const privacyTags = tags(privacy);
  for (const href of [GOOGLE_PRIVACY_URL, YOUTUBE_TERMS_URL]) {
    if (!hasLink(privacyTags, href)) errors.push(`privacy link: ${PRIVACY_PAGE} does not link ${href}`);
  }
}

let mode: WatchMode | undefined;
let thumbCount = 0;
const raw = readPage(WATCH_PAGE);

if (raw === undefined) {
  errors.push(`page: missing ${WATCH_PAGE}; run \`npm run build\` first`);
} else {
  // The client bundle is inlined into the page and holds template strings such
  // as data-testid="${...}" and the iframe it creates on Play, so markup checks
  // ignore every script body.
  const html = raw.replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, '');
  const all = tags(html);

  const roots = byTestId(all, TESTID.page);
  const modeValue = roots[0]?.attrs.get(ATTR.mode);
  if (roots.length !== 1) errors.push(`page: expected one ${TESTID.page} element, found ${roots.length}`);
  else if (modeValue === 'live' || modeValue === 'fixture' || modeValue === 'none') mode = modeValue;
  else errors.push(`page: ${TESTID.page} has ${ATTR.mode}="${modeValue ?? ''}", expected live, fixture or none`);

  if (DEPLOY && mode === 'fixture') errors.push('deploy: /watch was built from fixture data (WATCH_DATA=fixture); fixture data must never ship');

  // The player inserts its iframe only after Play.
  if (/<iframe\b/i.test(html)) errors.push(`iframe before Play: ${WATCH_PAGE} has an <iframe> outside script bodies`);

  const thumbs = byTestId(all, TESTID.thumb);
  thumbCount = thumbs.length;

  if (mode === 'none') {
    // One page-level empty state and no video markup.
    if (byTestId(all, TESTID.pageEmpty).length !== 1) errors.push(`empty state: none mode without exactly one ${TESTID.pageEmpty}`);
    if (thumbs.length > 0) errors.push(`empty state: none mode, but ${thumbs.length} ${TESTID.thumb} elements`);
    note = 'skipped: no video data';
  } else if (mode) {
    // Thumbnails are plain links to YouTube, so they work without JavaScript.
    if (thumbs.length === 0) {
      // A YouTube outage (every playlist empty or failed) must still deploy
      // its empty states; fixture data always has videos.
      if (mode === 'live') warnings.push(`watch: live mode, but no ${TESTID.thumb} elements (every playlist empty or failed)`);
      else errors.push(`thumb link: ${mode} mode, but no ${TESTID.thumb} elements`);
    }
    for (const t of thumbs) {
      const href = t.attrs.get('href') ?? '';
      if (t.name !== 'a' || !href.startsWith(WATCH_URL_PREFIX)) {
        errors.push(`thumb link: ${TESTID.thumb} for video ${t.attrs.get(ATTR.videoId) ?? '?'} is <${t.name} href="${href}">, expected <a href="${WATCH_URL_PREFIX}...">`);
      }
    }

    // Read each playlist's status and count from its rendered panel.
    const optionSlugs = byTestId(all, TESTID.option).map((t) => t.attrs.get(ATTR.playlist) ?? '');
    const panelStarts = all.flatMap((t, i) => (t.attrs.get('data-testid') === TESTID.panel ? [i] : []));
    const rendered = panelStarts.map((start, n) => {
      const seg = all.slice(start, panelStarts[n + 1] ?? all.length);
      const count = byTestId(seg, TESTID.thumb).length;
      const hasList = byTestId(seg, TESTID.list).length > 0;
      const hasEmpty = byTestId(seg, TESTID.empty).length > 0;
      let status: PlaylistStatus | 'unknown' = 'unknown';
      if (hasList && !hasEmpty) status = 'ok';
      else if (hasEmpty && !hasList) status = linksTo(seg, PLAYLIST_URL_PREFIX) ? 'failed' : 'empty';
      return { slug: all[start].attrs.get(ATTR.playlist) ?? '', status, count };
    });

    const panelSlugs = rendered.map((r) => r.slug);
    if (panelSlugs.join() !== optionSlugs.join()) errors.push(`menu/panels mismatch: menu options [${optionSlugs.join(', ')}] do not match panels [${panelSlugs.join(', ')}]`);
    const outside = thumbs.length - rendered.reduce((n, r) => n + r.count, 0);
    if (outside > 0) errors.push(`panels: ${outside} ${TESTID.thumb} elements sit outside any ${TESTID.panel}`);
    for (const r of rendered) if (r.status === 'unknown') errors.push(`panels: panel ${r.slug} has neither a ${TESTID.list} nor a ${TESTID.empty}, or both`);

    if (mode === 'fixture') {
      const want = FIXTURE_PLAYLISTS.map((e) => e.slug);
      if (optionSlugs.join() !== want.join()) errors.push(`fixture: menu options are [${optionSlugs.join(', ')}], expected [${want.join(', ')}]`);
      for (const e of FIXTURE_PLAYLISTS) {
        const r = rendered.find((x) => x.slug === e.slug);
        if (r && (r.status !== e.status || r.count !== e.videoIds.length)) {
          errors.push(`fixture: panel ${e.slug} is ${r.status} with ${r.count} thumbs, expected ${e.status} with ${e.videoIds.length}`);
        }
      }
    } else {
      // A single playlist failing must not block a deploy; it shows its own empty state.
      for (const r of rendered) if (r.status === 'empty' || r.status === 'failed') warnings.push(`watch playlist ${r.slug} is ${r.status}`);
    }
  }
}

for (const w of warnings) console.log(`::warning::${w}`);
if (note) console.log(note);
if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}
console.log(`check-watch-page: mode=${mode} thumbs=${thumbCount} files scanned=${files.length} ok`);

// Checks built HTML and the committed flyer files, so run after `astro build`.
// An open petition must ship a current flyer PDF that its page links; a closed
// one must have no flyer page and no PDF link, though its files may stay (A4).
// Not in `inv check`: a pledge edit would then block every commit until
// Chromium had rendered a new PDF (A11).
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import {
  FLYERS_DIR,
  flyerFingerprint,
  flyerPagePath,
  flyerPdfPath,
  flyerState,
  listPetitionActions,
  petitionUrl,
  type FlyerManifest,
} from '../src/lib/flyer';

// Override only to run the check against a scratch copy of the build.
const DIST = process.env.FLYER_CHECK_DIST ?? 'dist';
// The flyer is a print copy: no form, no live names or count, no Worker or
// Turnstile call (A16).
const FORBIDDEN = ['<form', 'data-names', 'petition-roll', 'data-count', 'api.dangerousrobot.org', 'challenges.cloudflare.com'];
const RERUN = 'run `inv flyers` and commit public/flyers/';

const errors: string[] = [];
let current = 0;
let closed = 0;

const builtPage = (path: string) => join(DIST, path.replace(/^\//, ''), 'index.html');

const actions = listPetitionActions().filter((a) => !a.draft);

for (const { slug, text } of actions) {
  const url = petitionUrl(slug);
  const pagePath = builtPage(`/petitions/${slug}`);
  const flyerPage = builtPage(flyerPagePath(slug));
  const pdfLink = `href="${flyerPdfPath(slug)}"`;

  if (!existsSync(pagePath)) {
    errors.push(`petition ${slug}: missing ${pagePath}; run \`npm run build\` first`);
    continue;
  }
  const page = readFileSync(pagePath, 'utf8');

  if (page.includes('data-status="closed"')) {
    closed++;
    if (page.includes(pdfLink)) errors.push(`closed petition ${slug}: the page links the flyer PDF`);
    if (existsSync(flyerPage)) errors.push(`closed petition ${slug}: ${flyerPage} exists; flyer.astro must drop closed petitions (A4)`);
    continue;
  }

  const manifestPath = join(FLYERS_DIR, `${slug}.json`);
  let state: ReturnType<typeof flyerState>;
  let manifest: Partial<FlyerManifest> | undefined;
  try {
    state = flyerState(slug, flyerFingerprint(text, url));
    if (existsSync(manifestPath)) manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as Partial<FlyerManifest>;
  } catch (e) {
    errors.push(`petition ${slug}: ${manifestPath} is not valid JSON (${(e as Error).message}); ${RERUN}`);
    continue;
  }

  if (state === 'current') current++;
  else errors.push(`petition ${slug}: flyer is ${state}; ${RERUN}`);
  if (manifest && manifest.url !== url) errors.push(`petition ${slug}: ${manifestPath} has url ${manifest.url ?? '(none)'}, expected ${url}; ${RERUN}`);

  if (!existsSync(flyerPage)) {
    errors.push(`petition ${slug}: missing ${flyerPage}`);
  } else {
    const flyer = readFileSync(flyerPage, 'utf8');
    if (!flyer.includes('class="petition-qr')) errors.push(`petition ${slug}: ${flyerPage} has no QR figure (class="petition-qr)`);
    for (const s of FORBIDDEN) if (flyer.includes(s)) errors.push(`petition ${slug}: ${flyerPage} contains "${s}" (A16)`);
  }

  if (!page.includes(pdfLink)) errors.push(`petition ${slug}: ${pagePath} does not link ${flyerPdfPath(slug)}`);
}

// A renamed, drafted or deleted petition leaves files nobody checks (A14).
const owned = new Set(actions.flatMap(({ slug }) => [`${slug}.pdf`, `${slug}.json`]));
if (existsSync(FLYERS_DIR)) {
  for (const name of readdirSync(FLYERS_DIR).sort()) {
    if (!owned.has(name)) errors.push(`orphan flyer ${FLYERS_DIR}/${name}: delete it`);
  }
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}
console.log(`flyers: ${current} petition(s) current, ${closed} closed`);

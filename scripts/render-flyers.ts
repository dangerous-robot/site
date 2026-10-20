// Renders each open petition's flyer page from a built site to a one-page US
// Letter PDF under public/flyers/, plus a fingerprint manifest that
// check:flyers compares. Run through `inv flyers`, which builds first and sets
// TZ=UTC. Usage: tsx scripts/render-flyers.ts --dist <built site dir>
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, statSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chromium, type Browser } from '@playwright/test';
import {
  FLYERS_DIR,
  flyerFingerprint,
  flyerPagePath,
  listPetitionActions,
  pdfPageCount,
  petitionUrl,
  writeFlyerManifest,
} from '../src/lib/flyer';

const ORIGIN = 'http://flyer.local';
const TMP_DIR = 'node_modules/.cache/flyers';

function fail(message: string): never {
  console.error(message);
  process.exit(1);
}

const distArg = process.argv[process.argv.indexOf('--dist') + 1];
if (!process.argv.includes('--dist') || !distArg) fail('usage: tsx scripts/render-flyers.ts --dist <dir>');
// Absolute, so the containment test below compares like with like.
const dir = path.resolve(distArg);

// Machine details a PDF must never carry into a public, committed file.
const machineStrings: [string, string][] = (
  [['hostname', os.hostname()], ['user name', os.userInfo().username], ['home directory', os.homedir()]] as [string, string][]
).filter(([, value]) => value.length > 0);

function localFile(pathname: string): string | null {
  let p: string;
  try {
    p = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  let file = path.resolve(dir, '.' + p);
  if (!file.startsWith(dir + path.sep)) return null;
  if (existsSync(file) && statSync(file).isDirectory()) file = path.join(file, 'index.html');
  return existsSync(file) && statSync(file).isFile() ? file : null;
}

// Throwing (not exiting) inside the loop lets the finally close Chromium.
class Refusal extends Error {}

async function render(browser: Browser, slug: string, tmp: string): Promise<string[]> {
  const foreign: string[] = [];
  const context = await browser.newContext({ colorScheme: 'light', serviceWorkers: 'block' });
  try {
    const page = await context.newPage();
    // Every request is answered here; nothing reaches the network.
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== ORIGIN) {
        foreign.push(url.href);
        return route.fulfill({ status: 404 });
      }
      const file = localFile(url.pathname);
      return file ? route.fulfill({ path: file }) : route.fulfill({ status: 404 });
    });
    // goto does not throw on a 404, and a 404's empty body prints as a blank
    // page that passes every gate below.
    const response = await page.goto(ORIGIN + flyerPagePath(slug), { waitUntil: 'load' });
    if (!response?.ok()) {
      throw new Refusal(`flyer page for ${slug} answered ${response?.status() ?? 'nothing'}: is the petition closed, or did the build fail?`);
    }
    await page.evaluate(() => document.fonts.ready.then(() => undefined));
    await page.pdf({ path: tmp, format: 'Letter', printBackground: true, preferCSSPageSize: true });
  } finally {
    await context.close();
  }
  return foreign;
}

const actions = listPetitionActions().filter((a) => !a.draft);
mkdirSync(TMP_DIR, { recursive: true });
mkdirSync(FLYERS_DIR, { recursive: true });

let browser: Browser;
try {
  browser = await chromium.launch();
} catch (err) {
  console.error(err instanceof Error ? err.message : err);
  fail('Chromium did not start: run npx playwright install chromium');
}

try {
  for (const { slug, text } of actions) {
    const built = path.join(dir, 'petitions', slug, 'index.html');
    if (!existsSync(built)) throw new Refusal(`no built page for ${slug} at ${built}: build the site first`);
    if (readFileSync(built, 'utf8').includes('data-status="closed"')) {
      console.log(`skip ${slug}: closed (A4)`);
      continue;
    }
    // The petition page and the flyer route each fetch the petition state at
    // build time, so they can disagree; an open page with no flyer is refused.
    const flyerBuilt = path.join(dir, 'petitions', slug, 'flyer', 'index.html');
    if (!existsSync(flyerBuilt)) {
      throw new Refusal(`no flyer page for ${slug} at ${flyerBuilt}: is the petition closed, or did the build fail?`);
    }

    // Rendered aside and moved only once every gate passes, so a refusal
    // leaves the committed PDF and manifest untouched.
    const tmp = path.join(TMP_DIR, `${slug}.pdf`);
    rmSync(tmp, { force: true });
    try {
      const foreign = await render(browser, slug, tmp);
      if (foreign.length > 0) throw new Refusal(`flyer for ${slug} requested ${foreign.length} foreign URL(s): ${foreign.join(', ')}`);

      const pdf = readFileSync(tmp);
      const pages = pdfPageCount(pdf);
      if (pages !== 1) {
        throw new Refusal(`flyer for ${slug} runs to ${pages} pages: shorten the text or apply the shrink order in src/pages/petitions/[slug]/flyer.astro`);
      }
      const bytes = pdf.toString('latin1');
      const leaked = machineStrings.filter(([, value]) => bytes.includes(value)).map(([label]) => label);
      if (leaked.length > 0) throw new Refusal(`flyer for ${slug} embeds a machine name or path (${leaked.join(', ')})`);

      const out = path.join(FLYERS_DIR, `${slug}.pdf`);
      renameSync(tmp, out);
      const url = petitionUrl(slug);
      writeFlyerManifest({ slug, url, fingerprint: flyerFingerprint(text, url), generated: new Date().toISOString() });
      console.log(out);
      console.log(path.join(FLYERS_DIR, `${slug}.json`));
    } finally {
      rmSync(tmp, { force: true });
    }
  }
} catch (err) {
  if (!(err instanceof Refusal)) throw err;
  console.error(err.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}

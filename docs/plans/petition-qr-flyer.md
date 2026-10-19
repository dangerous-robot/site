# Pledge QR code and print flyer

**Status**: `ready` (approved by Brandon 2026-10-18 with the agent's calls A1 to A11 as written; roadmap item SITE-BC (Pledge QR code and print flyer); see Review history)
**Last updated**: 2026-10-18

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A petition page shows a scannable QR code for its own URL beside the signature tally, and links a committed one-page US Letter PDF flyer of the petition (text, QR code, logo; no sign form) that an `inv` task regenerates and a build check keeps current.

**Architecture:** A build-time helper turns a URL into an inline QR SVG with the DR logo in the centre; a small component shows it in the sign block and on a new `noindex` flyer page per petition. An operator task builds the site, renders the flyer page to PDF with Playwright (already installed for the e2e tests) and writes the PDF plus a fingerprint manifest under `public/flyers/`. A check script run by `npm run check` and both workflows fails when a published petition's PDF is missing or older than its source text, its URL or the flyer template, so an edit cannot ship with an old flyer.

**Tech Stack:** Astro 7, `qrcode` (npm, SVG output, CommonJS), `@playwright/test` (Chromium `page.pdf`), `node:test` for unit tests, `tsx` scripts, Invoke task.

**Spec:** this file, § Design. The design was agreed in chat and has no separate document.

## Status checklist

Ticked as tasks land (AGENTS.md rule 4). Task ids are the headings below.

- [x] T0: Promote the plan and register the work item (2026-10-18)
- [ ] T1: QR SVG helper (`src/lib/qr.ts`)
- [ ] T2: Flyer files helper (`src/lib/flyer.ts`)
- [ ] T3: `PetitionQr` component in the sign block
- [ ] T4: Flyer page route, out of the sitemap
- [ ] T5: `inv flyers` render task; first PDF committed
- [ ] T6: `check:flyers` in the check chain and both workflows
- [ ] T7: Docs, backlog, finish

## Decisions

| # | Question | Answer (Brandon, 2026-10-18) |
|---|---|---|
| 1 | How the PDF is produced | A script renders it with Playwright; the PDF is committed under `public/`; a build check warns when it is older than the pledge file. No browser install in CI |
| 2 | Paper size | US Letter, portrait |
| 3 | URL in the QR code | The plain page URL, no tracking parameter |
| 4 | Flyer content | Title, byline, pledge statement, definitions, QR code with the URL under it, DR logo. No article image, no form, no live count |
| 5 | Release | Minor; rides the beta line as SITE-BC (Pledge QR code and print flyer) |

Calls made by the agent (override freely):

| # | Call |
|---|---|
| A1 | QR error correction level H, so the logo may cover the centre. Logo square is 22% of the code's width on a white square 1.12 times the logo; H tolerates about 30% damage. `qrcode`'s default quiet zone of 4 modules is kept |
| A2 | The logo is the black-on-transparent `public/dr-logo.png`, referenced by path, on both the site and the flyer (black on white scans in every theme) |
| A3 | On the page, the QR code sits in the tally column under the count and status chip, with the URL in small text under it and the flyer link as its caption. In dark mode the code keeps a white tile |
| A4 | The QR code and the flyer link are hidden when the build-time snapshot says the petition is closed (a poster inviting signatures to a closed petition is wrong). No snapshot (Worker down): shown. The PDF stays in the repo; `check:flyers` then requires the link to be absent and asks nothing else of that petition |
| A5 | The flyer page keeps the article body as written, including its final "Please consider adding yourself as a signatory." line, and shows the byline with "with AI assistance" when the post is flagged, as the page does |
| A6 | Link text "Print a flyer (PDF)". Brandon asked for "print flyer (or better)"; change the one constant if a better phrase comes up |
| A7 | The PDF is keyed by the page slug (the action id), not the Worker petition slug; they are equal today but mean different things. Action file names are lowercase kebab-case, so the file name and the collection id agree (`listPetitionActions` reads file names) |
| A8 | The fingerprint covers the action's Markdown text, the encoded URL, and the flyer templates (`src/pages/petitions/[slug]/flyer.astro`, `src/components/PetitionQr.astro`, `src/lib/qr.ts`), so a layout or URL change also trips the check. Global CSS changes do not; rerun `inv flyers` after those by hand |
| A9 | The render script serves the built site to Chromium from disk through a Playwright route handler, so no preview server or port is needed |
| A10 | URL form. The site is `trailingSlash: "never"` today and SITE-Z (Trailing-slash URLs) will flip it to `"always"` within this beta. The QR code and the printed URL carry the no-slash form `https://dangerousrobot.org/petitions/{slug}`. The site deploys to GitHub Pages (`deploy.yml`), which is expected to answer the slashless URL with a 301 to the slash form once `petitions/{slug}/index.html` exists; paper copies then survive the flip. Expected, not verified: Operator step 5 checks it after SITE-Z deploys. Internal paths in this plan are slashless (`/petitions/{slug}/flyer`); the render script serves `/x` and `/x/` alike. After SITE-Z lands, the manifest's stored URL stays valid and nothing needs rerunning |
| A11 | Where `check:flyers` runs. The pre-commit hook runs `inv check` on every commit, so putting the check there would block any commit that touches a petition's Markdown (a one-word fix included) until Chromium has rendered a new PDF. Brandon chose a check that "warns"; the plan therefore runs `check:flyers` in `npm run check`, `ci.yml` and `deploy.yml` (a stale flyer can be committed, never shipped) and leaves `inv check` alone. Brandon may move it into `inv check` if he prefers the hard stop |

## Design

**Page.** `/petitions/{slug}` gains, inside the sign block's tally column, a figure: the QR SVG (about 9rem square on a white tile), the page URL without scheme in small muted text, and a link "Print a flyer (PDF)" to `/flyers/{slug}.pdf`. The link appears only when that PDF exists in `public/flyers/` at build time, so a new petition never shows a dangling link. Both are hidden when the petition is closed (A4).

**Flyer page.** `/petitions/{slug}/flyer` renders with `Base` (`chrome="minimal"`, `layout="bare"`, `noindex`) and is excluded from the sitemap. Its root `<div class="flyer" data-theme="light">` also sets `background: #fff; color: var(--color-text)` explicitly, since `color` inherits from `body` and the viewer's theme may be dark. Base's accessibility control (`.a11y-root`, fixed, z-index 200) and the site footer are hidden on this page. Layout for one Letter page: `@page { size: 8.5in 11in; margin: 0 }`; a `.flyer` box 8.5in wide, 11in tall, 0.7in padding. Top to bottom: title in the display face; byline; the petition statement in a block with the accent top border the sign block uses; the body (the "Definitions" heading and four paragraphs); a bottom row with the QR code (1.7in) on the left and, on the right, "Sign the pledge", "Scan the code or go to", the URL, then the logo (0.5in) with "dangerousrobot.org". Text sizes: title about 26pt, statement 14pt, body 10.5pt. The render script refuses a PDF with more than one page.

**Files under `public/flyers/`.** `{slug}.pdf` and `{slug}.json` (`{ "slug", "url", "fingerprint", "generated" }`), both committed. `inv flyers` regenerates every published petition's pair.

**Check.** `npm run check:flyers`, after `npm run build`, for every non-draft action with a `petition` field: if the built page's status chip says closed, the page must not link the PDF and the rest is skipped; otherwise the PDF exists, the manifest's fingerprint and URL match the current ones, `dist/petitions/{slug}/flyer/index.html` exists, contains the QR figure and no `<form`, and `dist/petitions/{slug}/index.html` links the PDF. Any failure names `inv flyers`.

## Global Constraints

- Node `>=22.12.0`; Astro `^7.3.8`; new dependencies `qrcode@^1.5.4` (runtime) and `@types/qrcode@^1.5.5` (dev). No other new packages. `qrcode` is CommonJS with no `exports` map: use `import QRCode from 'qrcode'` (default import), which works under the Astro build and `tsx --test`.
- `src/lib/petition.ts` ships to the browser and must stay free of Node APIs; the new helpers go in their own files.
- Site unit tests use `node:test` via `npm run test:site` (`src/lib/**/*.test.ts`).
- The flyer page is `noindex` and out of the sitemap; `public/robots.txt` is unchanged.
- Copy: "Print a flyer (PDF)" (A6); "Sign the pledge"; "Scan the code or go to".
- No `cd &&` in Invoke tasks or docs; `inv flyers` runs from the repo root.
- Commits: conventional commits; explicit paths only (peers may share the checkout); every commit message ends with the `Co-Authored-By` trailer the session requires. Each task's commit also stages `docs/plans/petition-qr-flyer.md` (ticked checklist) and `docs/v1.0.0-roadmap.md` (SITE-BC checklist), per AGENTS.md rule 4.
- The pre-commit hook runs `inv check` on every commit (`check:flyers` is not part of it, A11). Temporary edits made for a verification step (T3 step 5 stub, T5 step 7 spacer) must never be staged; revert them before committing.
- Code edits need the work item registered (done in T0; `python3 scripts/release-gate/work_item.py status` shows SITE-BC with this plan's path).

## Review Focus

1. The pledge text is edited and deployed without rerunning `inv flyers`: `check:flyers` must fail in CI with a message naming `inv flyers` (T6 step 2, which edits the Markdown, not the manifest).
2. A new petition is published before anyone renders its flyer: the page must show the QR code with no flyer link, and `check:flyers` must fail for the missing PDF (T3 step 4, T6 step 3).
3. A closed petition: the QR code and the flyer link disappear, the rest of the sign block is unchanged, and `check:flyers` passes (T3 step 5, T6 step 4).
4. Dark mode and high-contrast themes: the QR code stays black on white and the logo stays black; the flyer page prints light whatever the viewer's theme (T3 step 6, T4 step 4).
5. A longer statement or an extra definition pushes the flyer to two pages: the render script must refuse to write a two-page PDF, leave the committed PDF untouched, and say what to shorten (T5 step 7).

---

### T0: Promote the plan and register the work item

Runs once Brandon approves this draft.

- [x] **Step 1:** Add a row to `## Review history` below for Brandon's review (`reviewed`, scope `full`).
- [x] **Step 2:** `git mv docs/plans/drafts/petition-qr-flyer.md docs/plans/petition-qr-flyer.md` (drafts are gitignored; `git mv` of an untracked file fails, so `mv` then `git add` the new path). Update the plan link in the SITE-BC section of `docs/v1.0.0-roadmap.md`.
- [x] **Step 3:** `python3 scripts/release-gate/work_item.py finish` (clears the draft-path registration), then `python3 scripts/release-gate/work_item.py start --title "SITE-BC (Pledge QR code and print flyer)" --kind minor --release v1.0.0 --plan docs/plans/petition-qr-flyer.md`.
- [x] **Step 4:** Commit: `git add docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md` then `git commit -m "docs(plans): petition QR code and flyer plan (SITE-BC)"`.

### T1: QR SVG helper

**Files:**
- Create: `src/lib/qr.ts`
- Test: `src/lib/qr.test.ts`
- Modify: `package.json` (dependencies), `package-lock.json`

**Interfaces:**
- Consumes: `qrcode` (`QRCode.toString(text, { type: 'svg', errorCorrectionLevel: 'H' })` resolves to an SVG string with `viewBox="0 0 N N"`, N = modules plus the default 4-module margin on each side, containing a background path and the dark-module path).
- Produces: `export async function qrSvg(url: string): Promise<string>`; `export const QR_LOGO_HREF = '/dr-logo.png'`; `export const QR_LOGO_FRACTION = 0.22`. The returned SVG has `role="img"`, an `<title>` "QR code for {url}" as its first child, `qrcode`'s background and module paths, then a white `<rect>` and an `<image href="/dr-logo.png">` centred, sized from `QR_LOGO_FRACTION` of the viewBox width (the rect 1.12 times the image).

- [ ] **Step 1: Add the dependency**

```bash
npm install qrcode@^1.5.4
npm install --save-dev @types/qrcode@^1.5.5
```

- [ ] **Step 2: Write the failing tests**

```ts
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { qrSvg, QR_LOGO_FRACTION, QR_LOGO_HREF } from './qr';

const URL = 'https://dangerousrobot.org/petitions/prohibit-ai-self-improvement';

describe('qrSvg', () => {
  test('is one svg with a title naming the url', async () => {
    const svg = await qrSvg(URL);
    assert.match(svg, /^<svg[^>]*role="img"/);
    assert.match(svg, new RegExp(`<title>QR code for ${URL}</title>`));
  });
  test('centres the logo on a white square inside the H-level limit', async () => {
    const svg = await qrSvg(URL);
    const [, size] = svg.match(/viewBox="0 0 (\d+) \1"/)!;
    const n = Number(size);
    const img = svg.match(/<image href="([^"]+)" width="([\d.]+)" height="([\d.]+)" x="([\d.]+)" y="([\d.]+)"/)!;
    assert.equal(img[1], QR_LOGO_HREF);
    const w = Number(img[2]);
    assert.equal(w, Number(img[3]));
    assert.ok(Math.abs(w / n - QR_LOGO_FRACTION) < 0.01);
    assert.ok(Math.abs(Number(img[4]) + w / 2 - n / 2) < 0.01, 'x centred');
    assert.ok(Math.abs(Number(img[5]) + w / 2 - n / 2) < 0.01, 'y centred');
    assert.match(svg, /<rect [^>]*fill="#fff"/);
    assert.ok((w * 1.12) ** 2 / n ** 2 < 0.3, 'covered area under the 30% H tolerance');
  });
  test('refuses a non-https url', async () => {
    await assert.rejects(qrSvg('javascript:alert(1)'));
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `npm run test:site`
Expected: FAIL, `Cannot find module './qr'`.

- [ ] **Step 4: Implement `qrSvg(url: string): Promise<string>` in `src/lib/qr.ts`**

Throw on a URL whose `protocol` is not `https:`. Write the `<image>` attributes in the order `href`, `width`, `height`, `x`, `y`, as the test reads them. Insert the rect and image before the closing `</svg>` of the string `qrcode` returns, and add `role="img"` and the `<title>` to that string.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm run test:site`
Expected: PASS, three `qrSvg` tests.

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json src/lib/qr.ts src/lib/qr.test.ts docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(site): QR SVG helper with the DR logo in the centre (SITE-BC)"
```

### T2: Flyer files helper

**Files:**
- Create: `src/lib/flyer.ts`
- Test: `src/lib/flyer.test.ts`

**Interfaces:**
- Consumes: `node:fs`, `node:crypto`, `node:path`, `js-yaml` (already a dependency) for the front matter block.
- Produces (Node-only; never import from browser code):
  - `export const FLYER_LINK_TEXT = 'Print a flyer (PDF)'`
  - `export const FLYERS_DIR = 'public/flyers'`
  - `export const FLYER_TEMPLATE_FILES = ['src/pages/petitions/[slug]/flyer.astro', 'src/components/PetitionQr.astro', 'src/lib/qr.ts']`
  - `export const flyerPdfPath = (slug: string): string => \`/flyers/${slug}.pdf\`` (site path)
  - `export const flyerPagePath = (slug: string): string => \`/petitions/${slug}/flyer\``
  - `export interface FlyerManifest { slug: string; url: string; fingerprint: string; generated: string }`
  - `export interface PetitionAction { slug: string; draft: boolean; text: string }` (`text` is the whole file's contents)
  - `export function listPetitionActions(actionsDir = 'src/content/actions'): PetitionAction[]` (every `*.md` whose front matter has a `petition` key; `slug` is the file name without `.md`; `draft` from front matter, default false)
  - `export function flyerFingerprint(text: string, url: string, templateFiles: string[] = FLYER_TEMPLATE_FILES): string` (sha256 hex over `text`, `url` and each template file's contents, joined with `\0`; a template file that does not exist contributes an empty string)
  - `export function flyerState(slug: string, fingerprint: string, flyersDir = FLYERS_DIR): 'missing' | 'stale' | 'current'` (`missing` when the PDF or manifest is absent; `stale` when the manifest's fingerprint differs)
  - `export function writeFlyerManifest(manifest: FlyerManifest, flyersDir = FLYERS_DIR): void` (writes `{slug}.json`, two-space indented, trailing newline)
  - `export function pdfPageCount(pdf: Buffer): number` (count of `/Type /Page` objects that are not `/Pages`; Chromium writes these headers uncompressed; regex `/\/Type\s*\/Page(?![s\w])/g`)

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { listPetitionActions, flyerFingerprint, flyerState, writeFlyerManifest, pdfPageCount, flyerPdfPath, flyerPagePath } from './flyer';

let actions: string;
let flyers: string;
beforeEach(() => {
  actions = mkdtempSync(join(tmpdir(), 'actions-'));
  flyers = mkdtempSync(join(tmpdir(), 'flyers-'));
  writeFileSync(join(actions, 'pledge.md'), '---\ntitle: P\npetition: x\n---\nbody\n');
  writeFileSync(join(actions, 'draft.md'), '---\ntitle: D\npetition: y\ndraft: true\n---\n');
  writeFileSync(join(actions, 'note.md'), '---\ntitle: N\n---\nno petition\n');
});
afterEach(() => { rmSync(actions, { recursive: true }); rmSync(flyers, { recursive: true }); });

describe('flyer helpers', () => {
  test('listPetitionActions keeps files with a petition key and reads draft and text', () => {
    const list = listPetitionActions(actions);
    assert.deepEqual(list.map((a) => [a.slug, a.draft]).sort(), [['draft', true], ['pledge', false]]);
    assert.equal(list.find((a) => a.slug === 'pledge')!.text, '---\ntitle: P\npetition: x\n---\nbody\n');
  });
  test('flyerFingerprint changes with the text, the url or a template, and is 64 hex chars', () => {
    const tpl = join(actions, 'tpl.astro');
    writeFileSync(tpl, 'a');
    const base = flyerFingerprint('t', 'https://x/p', [tpl]);
    assert.match(base, /^[0-9a-f]{64}$/);
    assert.notEqual(base, flyerFingerprint('t ', 'https://x/p', [tpl]));
    assert.notEqual(base, flyerFingerprint('t', 'https://x/p/', [tpl]));
    writeFileSync(tpl, 'b');
    assert.notEqual(base, flyerFingerprint('t', 'https://x/p', [tpl]));
  });
  test('flyerState is missing without a pdf or manifest, current after writeFlyerManifest, stale on a new fingerprint', () => {
    assert.equal(flyerState('pledge', 'f1', flyers), 'missing');
    writeFileSync(join(flyers, 'pledge.pdf'), '%PDF-1.4');
    assert.equal(flyerState('pledge', 'f1', flyers), 'missing');
    writeFlyerManifest({ slug: 'pledge', url: 'https://x/p', fingerprint: 'f1', generated: '2026-10-18T00:00:00Z' }, flyers);
    assert.equal(flyerState('pledge', 'f1', flyers), 'current');
    assert.equal(flyerState('pledge', 'f2', flyers), 'stale');
  });
  test('pdfPageCount counts page objects, not the Pages tree', () => {
    const one = Buffer.from('%PDF-1.4\n1 0 obj << /Type /Pages /Kids [2 0 R] >>\n2 0 obj << /Type /Page /Parent 1 0 R >>\n');
    const two = Buffer.concat([one, Buffer.from('3 0 obj << /Type /Page /Parent 1 0 R >>\n')]);
    assert.equal(pdfPageCount(one), 1);
    assert.equal(pdfPageCount(two), 2);
  });
  test('paths', () => {
    assert.equal(flyerPdfPath('p'), '/flyers/p.pdf');
    assert.equal(flyerPagePath('p'), '/petitions/p/flyer');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm run test:site`
Expected: FAIL, `Cannot find module './flyer'`.

- [ ] **Step 3: Implement the functions above in `src/lib/flyer.ts`**

Front matter: the text between the first two `---` lines, parsed with `js-yaml` `load`; a file without a block or without `petition` is skipped.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm run test:site`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/flyer.ts src/lib/flyer.test.ts docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(site): flyer path, fingerprint and manifest helpers (SITE-BC)"
```

### T3: `PetitionQr` component in the sign block

**Files:**
- Create: `src/components/PetitionQr.astro`
- Modify: `src/components/PetitionSign.astro` (props, tally column markup, styles), `src/pages/petitions/[slug].astro` (pass `pageUrl` and `flyerHref`)

**Interfaces:**
- Consumes: `qrSvg` (T1); `flyerPdfPath`, `FLYER_LINK_TEXT`, `FLYERS_DIR` (T2); `petitionHref` from `src/lib/actions.ts`; `Astro.site`.
- Produces: `PetitionQr.astro` with `interface Props { url: string; flyerHref?: string; size?: 'page' | 'flyer' }` rendering `<figure class="petition-qr" data-size={size}>` containing `<div class="petition-qr__tile">` with the SVG (`set:html`), `<p class="petition-qr__url">` with the URL minus `https://`, and, when `flyerHref` is set, `<figcaption><a href={flyerHref}>{FLYER_LINK_TEXT}</a></figcaption>` (no `download` attribute: the browser's PDF viewer has Print one click away). `PetitionSign.astro` gains props `pageUrl: string` and `flyerHref?: string` and renders `<PetitionQr>` at the end of `.petition-tally`, wrapped in `{!closed && (...)}`. The page computes `pageUrl = new URL(petitionHref(action), Astro.site).href` (no trailing slash, A10).

- [ ] **Step 1: Take the baseline**

There is no component test runner; the check is the built HTML (T6's `check-flyers.ts` makes it permanent). Build and grep:

Run: `npm run build && grep -c 'class="petition-qr' dist/petitions/prohibit-ai-self-improvement/index.html`
Expected before the change: `0`.

- [ ] **Step 2: Create `PetitionQr.astro`**

Styles (scoped): `.petition-qr { display: grid; gap: var(--space-xs); justify-items: start; margin: var(--space-lg) 0 0; }`; `.petition-qr__tile { background: #fff; padding: var(--space-sm); width: 9rem; height: 9rem; box-sizing: border-box; }` with the SVG filling it (`svg { display: block; width: 100%; height: 100%; }`); `[data-size="flyer"] .petition-qr__tile { width: 1.7in; height: 1.7in; }`; `.petition-qr__url { margin: 0; font-size: var(--font-size-xs); color: var(--color-text-muted); overflow-wrap: anywhere; }`; the caption link uses the site's default link style at `font-size: var(--font-size-sm)`. The quiet zone is the code's own 4-module margin plus the tile padding.

- [ ] **Step 3: Wire it into the sign block and the page**

In `[slug].astro`: `const pageUrl = new URL(petitionHref(action), Astro.site).href;` and `const flyerHref = existsSync(join(FLYERS_DIR, \`${action.id}.pdf\`)) ? flyerPdfPath(action.id) : undefined;` passed to `<PetitionSign>`. In `PetitionSign.astro`: render `{!closed && <PetitionQr url={pageUrl} flyerHref={flyerHref} />}` after `.petition-tally__status`. The sign block's 640px breakpoint stacks the board into one column already; nothing else changes.

- [ ] **Step 4: Build and verify**

Run: `npm run build && grep -c 'class="petition-qr' dist/petitions/prohibit-ai-self-improvement/index.html && grep -c 'Print a flyer' dist/petitions/prohibit-ai-self-improvement/index.html`
Expected: `1` then `0` (no PDF exists yet, so no link: Review Focus 2). Also `npm run check:types` passes.

- [ ] **Step 5: Hidden when closed**

Temporarily point `PUBLIC_PETITION_API` at a local stub that returns `{"status":"closed","closed_at":"2026-10-01T00:00:00Z","count":3,"names":[]}` (for example `python3 -m http.server` in a scratchpad folder serving a `petitions/prohibit-ai-self-improvement` file), build, and confirm `grep -c 'class="petition-qr'` prints `0`. Record the result in the commit message body. Nothing from the stub is staged.

- [ ] **Step 6: Screenshot in light and dark mode**

With `inv dev` on port 4321, take `/petitions/prohibit-ai-self-improvement#sign` at 1200px and 400px widths, light and dark (`document.documentElement.dataset.theme = 'dark'`). Check: the QR tile is white in dark mode, the logo black, the code aligned with the count above it, no horizontal overflow at 400px. Keep the screenshots under the scratchpad and name them in the handoff note; the phone scan is an operator step.

- [ ] **Step 7: Commit**

```bash
git add src/components/PetitionQr.astro src/components/PetitionSign.astro src/pages/petitions/[slug].astro docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(site): QR code beside the petition tally (SITE-BC)"
```

### T4: Flyer page route, out of the sitemap

**Files:**
- Create: `src/pages/petitions/[slug]/flyer.astro`
- Modify: `astro.config.ts` (sitemap `filter`)

**Interfaces:**
- Consumes: `getActions`, `petitionHref` (`src/lib/actions.ts`); `render` from `astro:content`; `PetitionQr` (T3) with `size="flyer"`; `formatPostDate` (`src/lib/writing.ts`); `Base`.
- Produces: the route `/petitions/{slug}/flyer` (built as `dist/petitions/{slug}/flyer/index.html`) for every action with a `petition` field (drafts included in dev, dropped in production, as `getActions` does). Root element `<div class="flyer" data-theme="light">`.

- [ ] **Step 1: Create the page**

`getStaticPaths` mirrors `[slug].astro`. `<Base title={\`${title} flyer\`} description={description} layout="bare" chrome="minimal" noindex>`. Markup, top to bottom: `<h1>` title; `<p class="flyer__byline">` "Written by {author}{ai_assisted && ', with AI assistance'} · {formatPostDate(pubDate)}"; `<blockquote class="flyer__statement">` with `petition_statement` (omit the block when unset); `<div class="flyer__body"><Content /></div>`; `<footer class="flyer__sign">` with `<PetitionQr url={pageUrl} size="flyer" />`, `<h2>Sign the pledge</h2>`, `<p>Scan the code or go to</p>`, `<p class="flyer__url">{pageUrl without https://}</p>`, `<img src="/dr-logo.png" alt="" width="48" height="48"> dangerousrobot.org`. Styles per § Design: the Letter page box, `background: #fff; color: var(--color-text)` on `.flyer`, sizes in pt, `@page`, plus `@media screen { body { background: #888 } .flyer { margin: 2rem auto; box-shadow: 0 0 1rem rgb(0 0 0 / 0.3) } }` so the page previews as a sheet in a browser. Hide Base's footer and the accessibility control on this page: `:global(.a11y-root), :global(.site-footer) { display: none }` (check the footer's class name in `Base.astro` and use that).

- [ ] **Step 2: Exclude from the sitemap**

In `astro.config.ts`'s sitemap `filter`, as the first statement (before the `INDEX_ALPHA_DETAIL_PAGES` early return): `if (/\/flyer\/?$/.test(new URL(page).pathname)) return false;`. Sitemap entries have no trailing slash under `trailingSlash: "never"`, hence the optional slash.

- [ ] **Step 3: Build and verify**

Run: `npm run build && test -f dist/petitions/prohibit-ai-self-improvement/flyer/index.html && grep -c '<form' dist/petitions/prohibit-ai-self-improvement/flyer/index.html; grep -c 'noindex' dist/petitions/prohibit-ai-self-improvement/flyer/index.html; grep -c '/flyer<' dist/sitemap-0.xml`
Expected: `0`, `1`, `0`.

- [ ] **Step 4: Preview as a sheet, in dark mode too**

Open `http://localhost:4321/petitions/prohibit-ai-self-improvement/flyer` in Chrome with the site theme set to dark, then File > Print preview, Letter, no margins: one page, white background, dark text, nothing clipped, Space Grotesk headings. Adjust the pt sizes in the page's styles if it spills. Screenshot to the scratchpad.

- [ ] **Step 5: Commit**

```bash
git add src/pages/petitions/[slug]/flyer.astro astro.config.ts docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(site): one-page flyer route per petition (SITE-BC)"
```

### T5: `inv flyers` render task; first PDF committed

**Files:**
- Create: `scripts/render-flyers.ts`, `public/flyers/prohibit-ai-self-improvement.pdf`, `public/flyers/prohibit-ai-self-improvement.json`
- Modify: `tasks.py` (task `flyers`), `package.json` (`"flyers": "tsx scripts/render-flyers.ts"`)

**Interfaces:**
- Consumes: `chromium` from `@playwright/test`; `listPetitionActions`, `flyerPagePath`, `flyerFingerprint`, `writeFlyerManifest`, `pdfPageCount`, `FLYERS_DIR` (T2); `petitionHref` (`src/lib/actions.ts` imports `astro:content`, so the script builds the URL itself: `https://dangerousrobot.org/petitions/${slug}`, matching A10; put that one-liner in `src/lib/flyer.ts` as `export const petitionUrl = (slug: string) => \`https://dangerousrobot.org/petitions/${slug}\`` and have `[slug].astro` use the same function instead of `new URL(petitionHref(action), Astro.site)`, so the two cannot drift).
- Produces: `scripts/render-flyers.ts --dist <dir>`: for each non-draft petition action, opens `http://flyer.local{flyerPagePath(slug)}` in a fresh Chromium context (`colorScheme: 'light'`) with every request answered from `<dir>` by `page.route('**/*', ...)` (a path with or without a trailing slash that names a directory maps to its `index.html`; unknown paths get 404), waits for `document.fonts.ready`, then `page.pdf({ path: <tmp>, format: 'Letter', printBackground: true, preferCSSPageSize: true })` into a temporary file under `node_modules/.cache/flyers/`. If `pdfPageCount` is not 1: delete the temporary file, print "flyer for {slug} runs to N pages: shorten the text or the sizes in src/pages/petitions/[slug]/flyer.astro", exit 1, committed files untouched. Otherwise move it to `public/flyers/{slug}.pdf`, write the manifest (`url: petitionUrl(slug)`, `fingerprint: flyerFingerprint(text, url)`, `generated` ISO date-time) and print both paths. On a Chromium launch failure, print `npx playwright install chromium`.

- [ ] **Step 1: Add `petitionUrl` to `src/lib/flyer.ts` with a test, and switch `[slug].astro` to it**

Test: `assert.equal(petitionUrl('p'), 'https://dangerousrobot.org/petitions/p')`. Run `npm run test:site`: PASS.

- [ ] **Step 2: Write `scripts/render-flyers.ts`**

Per the Produces block.

- [ ] **Step 3: Add the Invoke task and npm script**

`tasks.py`, next to `check`:

```python
@task
def flyers(ctx):
    """Render each published petition's one-page flyer PDF into public/flyers/ (commit the result)."""
    out = "node_modules/.cache/flyers/dist"
    ctx.run(f"npm run build -- --outDir {out}", pty=True)
    ctx.run(f"npm run flyers -- --dist {out}", pty=True)
```

Register it with `ns.add_task(flyers)`.

- [ ] **Step 4: Render the first flyer**

Run: `inv flyers`
Expected: prints `public/flyers/prohibit-ai-self-improvement.pdf` and `.json`. Open the PDF: one Letter page, logo visible in the QR's centre, URL under it matches the page. `pdfinfo` or Preview shows 1 page and 8.5 x 11 in. The phone scan is an operator step.

- [ ] **Step 5: Confirm the page now links the PDF**

Run: `npm run build && grep -c 'href="/flyers/prohibit-ai-self-improvement.pdf"' dist/petitions/prohibit-ai-self-improvement/index.html`
Expected: `1`.

- [ ] **Step 6: Rerun is a no-op on the manifest fingerprint**

Run `inv flyers` again and `git diff --stat public/flyers/`: only `generated` changes in the JSON (the PDF bytes may differ by timestamp; that is fine).

- [ ] **Step 7: Refuses a second page**

Temporarily add `<p style="height: 6in"></p>` to the flyer body in `flyer.astro`, run `inv flyers`: exit code 1, the message names the slug and the file, and `git status public/flyers/` shows no change. Revert the temporary edit before committing.

- [ ] **Step 8: Commit**

```bash
git add scripts/render-flyers.ts src/lib/flyer.ts src/lib/flyer.test.ts src/pages/petitions/[slug].astro tasks.py package.json public/flyers/prohibit-ai-self-improvement.pdf public/flyers/prohibit-ai-self-improvement.json docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(ops): inv flyers renders the petition flyer PDF (SITE-BC)"
```

### T6: `check:flyers` in the check chain and both workflows

**Files:**
- Create: `scripts/check-flyers.ts`
- Modify: `package.json` (`check:flyers` script; append to `check`), `.github/workflows/ci.yml` and `.github/workflows/deploy.yml` (a `run: npm run check:flyers` step after `check:watch`). Not `tasks.py` `check` (A11)

**Interfaces:**
- Consumes: `listPetitionActions`, `flyerFingerprint`, `flyerState`, `flyerPdfPath`, `flyerPagePath`, `petitionUrl`, `FLYERS_DIR` (T2, T5). Env `FLYER_CHECK_DIST` overrides `dist`, as `WATCH_CHECK_DIST` does.
- Produces: exit 1 with one line per failure, each ending "run `inv flyers` and commit public/flyers/": for each non-draft petition action, read `dist/petitions/{slug}/index.html`; if it contains `data-status="closed"`, require that it does not contain `href="{flyerPdfPath(slug)}"` and continue to the next action; otherwise require `flyerState(slug, flyerFingerprint(text, petitionUrl(slug)))` is `current` (report `missing` or `stale`), the manifest's `url` equals `petitionUrl(slug)`, `dist/petitions/{slug}/flyer/index.html` exists, contains `class="petition-qr` and no `<form`, and the petition page contains `href="{flyerPdfPath(slug)}"`. Exit 0 prints "flyers: N petition(s) current, M closed".

- [ ] **Step 1: Write the script**

Same shape as `scripts/check-watch-page.ts`: collect `errors`, print, exit.

- [ ] **Step 2: Prove it fails on a stale flyer (Review Focus 1)**

Run `npm run build` once. Append one line to `src/content/actions/prohibit-ai-self-improvement.md`, run `npm run check:flyers`: exit 1, the message says `stale` and names `inv flyers`. Restore the file with `git checkout -- src/content/actions/prohibit-ai-self-improvement.md`.

- [ ] **Step 3: Prove it fails on a missing PDF (Review Focus 2)**

Move the PDF aside, run `npm run check:flyers`: exit 1, `missing`. Move it back.

- [ ] **Step 4: Prove a closed petition passes (Review Focus 3)**

With the closed stub from T3 step 5, build, run `npm run check:flyers`: exit 0, "1 closed". Rebuild without the stub.

- [ ] **Step 5: Prove it passes**

Run: `npm run check:flyers`
Expected: `flyers: 1 petition(s) current, 0 closed`, exit 0.

- [ ] **Step 6: Wire it in**

`package.json` `check` chain gets `&& npm run check:flyers` after `check:watch`; both workflows get the step after their `check:watch` step; `inv check` is left as is (A11). Run `uvx zizmor .github/workflows` to confirm the workflow edit adds no finding.

- [ ] **Step 7: Commit**

```bash
git add scripts/check-flyers.ts package.json .github/workflows/ci.yml .github/workflows/deploy.yml docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "ci: check:flyers fails when a petition flyer is missing or stale (SITE-BC)"
```

### T7: Docs, backlog, finish

**Files:**
- Modify: `docs/architecture/petitions.md` (Pieces table: QR component, flyer page, `public/flyers/`, render and check scripts; Routes: the flyer page), `docs/architecture/site.md` (the `npm run check` chain and CI step lists), `docs/runbook.md` ("Petitions" section: a "Flyer" paragraph: when to run `inv flyers`, commit `public/flyers/`, that `check:flyers` blocks a stale deploy; the phone-scan check after a rerun), `docs/UNSCHEDULED.md` (record any follow-up that came up during T1 to T6, with a triage marker; if none, no change, and say so in the commit body), `docs/v1.0.0-roadmap.md` (SITE-BC checklist, status `done` with commit refs), this plan (status checklist, Status line).

- [ ] **Step 1: Write the doc changes**
- [ ] **Step 2: Run `npm run check` end to end**

Expected: every step passes, including `check:flyers`.

- [ ] **Step 3: Commit, then finish the work item**

```bash
git add docs/architecture/petitions.md docs/architecture/site.md docs/runbook.md docs/UNSCHEDULED.md docs/v1.0.0-roadmap.md docs/plans/petition-qr-flyer.md
git commit -m "docs: petition QR code and flyer (SITE-BC)"
python3 scripts/release-gate/work_item.py finish
```

Then AGENTS.md rule 5: with every task ticked, `git mv docs/plans/petition-qr-flyer.md docs/plans/completed/` in a follow-up docs commit, fixing the roadmap link.

## Operator steps (Brandon)

1. Review this plan; T0 promotes it.
2. `npx playwright install chromium` once, if the e2e tests have never run on this machine.
3. After T3 lands: scan the QR code on the live or dev page with a phone, in dark mode too. After T5: scan the PDF's QR code from the screen and from a printed sheet at arm's length (the 1.7in code should scan from about 1m). Say "scanned OK" in the handoff note or the deploy commit.
4. Push and deploy as usual; the Worker is untouched.
5. After SITE-Z (Trailing-slash URLs) deploys: `curl -sI https://dangerousrobot.org/petitions/prohibit-ai-self-improvement | head -3` must show a 301 to the slash form (A10). If it does not, rerun `inv flyers` with `petitionUrl` changed to the slash form and reprint.

## Self-review (agent, 2026-10-18)

- Spec coverage: QR with logo (T1, T3), near the sign form (T3), PDF without the form and with the QR (T4, T5), linked with a "Print a flyer" caption (T3), committed script output (T5), staleness check (T6), US Letter (T4, T5), plain URL (T3, T5). No gap found.
- Names used across tasks: `qrSvg`, `QR_LOGO_HREF`, `QR_LOGO_FRACTION` (T1 → T3); `flyerPdfPath`, `flyerPagePath`, `FLYER_LINK_TEXT`, `FLYERS_DIR`, `FLYER_TEMPLATE_FILES`, `listPetitionActions` (`text`), `flyerFingerprint`, `flyerState`, `writeFlyerManifest`, `pdfPageCount`, `petitionUrl` (T2, T5 → T3, T5, T6). Consistent.
- Review Focus 1 to 5 each have a step: T6 step 2, T3 step 4 with T6 step 3, T3 step 5 with T6 step 4, T3 step 6 with T4 step 4, T5 step 7.

## Review history

| Date | Reviewer | Scope | Outcome |
|---|---|---|---|
| 2026-10-18 | agent (claude-opus-5-5), fresh-eyes builder check against the repo | full | iterated: fixed the sitemap filter for `trailingSlash: "never"`, settled the URL form against SITE-Z (A10), made a closed petition pass `check:flyers` (A4), renamed `source` to `text` and made the stale test edit the Markdown, widened the fingerprint to the templates and URL (A8), temp-file render, light colour scheme and hidden a11y control on the flyer, plan and roadmap staged in every commit, T0 promotion step, UNSCHEDULED.md step |
| 2026-10-18 | Brandon | full | approved as is, default answers to the four open calls (A11 check placement, A4 closed petition, A10 URL form, A8 fingerprint scope); promoted to `docs/plans/` |

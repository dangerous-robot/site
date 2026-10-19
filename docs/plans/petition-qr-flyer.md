# Pledge QR code and print flyer

**Status**: `in progress` (approved by Brandon 2026-10-18; revised the same day from three reviewer reports: calls A12 to A18 added, A1, A3, A4, A6, A10 rewritten; roadmap item SITE-BC (Pledge QR code and print flyer); see Review history)
**Last updated**: 2026-10-18

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A petition page shows a scannable QR code for its own URL beside the signature tally, and links a committed one-page US Letter PDF flyer of the petition (text, QR code, logo; no sign form) that an `inv` task regenerates and a build check keeps current.

**Architecture:** A build-time helper turns a URL into an inline QR SVG with the DR logo in the centre; a small component shows it in the sign block and on a new `noindex` flyer page per petition. A Playwright e2e test decodes the rendered codes with `zxing-wasm`, so the logo overlay can never ship an unreadable code. An operator task builds the site, renders the flyer page to PDF with Playwright (already installed for the e2e tests) and writes the PDF plus a fingerprint manifest under `public/flyers/`; the flyer uses only the site's shipped fonts, so the committed PDF is the same on every machine. A check script run by `npm run check` and both workflows fails when a published petition's PDF is missing or older than its source text, its URL or the flyer template, or when a flyer file has no live petition, so an edit cannot ship with an old flyer.

**Tech Stack:** Astro 7, `qrcode` (npm, SVG output, CommonJS), `@playwright/test` (Chromium `page.pdf`), `zxing-wasm` (dev, e2e QR decode), `@fontsource/space-grotesk` 400 (one more weight file of a font already installed), `node:test` for unit tests, `tsx` scripts, Invoke task, poppler `pdfinfo` and `pdffonts` on the operator machine (`/opt/homebrew/bin`).

**Spec:** this file, § Design. The design was agreed in chat and has no separate document.

## Status checklist

Ticked as tasks land (AGENTS.md rule 4). Task ids are the headings below.

- [x] T0: Promote the plan and register the work item (2026-10-18)
- [x] T1: QR SVG helper (`src/lib/qr.ts`)
- [x] T2: Flyer files helper (`src/lib/flyer.ts`)
- [x] T3: `PetitionQr` component in the sign block
- [x] T4: Flyer page route, out of the sitemap; QR decode e2e test
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
| A1 | QR error correction level H, so the logo may cover the centre. `QR_LOGO_FRACTION = 0.14`: the logo square is 14% of the code's viewBox width on a white square 1.12 times the logo. The limit is the artwork, not the codeword budget: the robot's eye (white ring, black pupil) resembles a finder pattern, and at 22% zxing-cpp failed to decode at every size tested while 13% to 14% decoded at every size (phone decoders were not tested; "likely to fail on some scanners"). The e2e decode test (A12) gates any later increase; masking the eye in the overlay is a brand change and Brandon's call (Q1). `qrcode`'s default quiet zone of 4 modules is kept |
| A2 | The logo is the black-on-transparent `public/dr-logo.png`, referenced by path, on both the site and the flyer (black on white scans in every theme) |
| A3 | On the page, the QR code sits at the end of the tally column, under the count and status chip: an 8rem bordered white tile and one caption sentence that carries the flyer link. No URL line (it is the page's own address). Below 640px the tile is hidden and only the flyer link line remains. In dark mode the tile stays white and the logo black, with no theme filter |
| A4 | A closed petition (build-time snapshot says `closed`) shows no QR code and no flyer link, and `check:flyers` requires `public/flyers/{slug}.pdf` and `.json` to be absent (git history keeps them; the failure message says to delete them), so a poster inviting signatures to a closed petition cannot stay public. `inv flyers` skips a closed petition and prints the skip. No snapshot (Worker down): shown and rendered as open |
| A5 | The flyer page keeps the article body as written, including its final "Please consider adding yourself as a signatory." line, and shows the byline with "with AI assistance" when the post is flagged, as the page does |
| A6 | Link text constant `FLYER_LINK_TEXT = 'print a flyer (PDF)'`, lower-case because it sits inside the caption sentence "Scan to open this page on a phone, or print a flyer (PDF)."; below 640px, where the link is the whole line, `::first-letter` capitalises it. Brandon asked for "print flyer (or better)"; change the one constant if a better phrase comes up |
| A7 | The PDF is keyed by the page slug (the action id), not the Worker petition slug; they are equal today but mean different things. Action file names are lowercase kebab-case, so the file name and the collection id agree (`listPetitionActions` reads file names and enforces that, A17) |
| A8 | The fingerprint covers the action's Markdown text, the encoded URL, and the flyer templates (`src/pages/petitions/[slug]/flyer.astro`, `src/components/PetitionQr.astro`, `src/lib/qr.ts`), so a layout or URL change also trips the check. Global CSS changes do not; rerun `inv flyers` after those by hand |
| A9 | The render script serves the built site to Chromium from disk through a Playwright route handler, so no preview server or port is needed; the handler is locked down per A16 |
| A10 | URL form. The site is `trailingSlash: "never"` today and SITE-Z (Trailing-slash URLs) will flip it to `"always"` within this beta. The QR code and the printed URL carry the no-slash form `https://dangerousrobot.org/petitions/{slug}`. Observed 2026-10-18 on the live site: `curl -sI` of that URL returns `HTTP/2 301` with `location: .../prohibit-ai-self-improvement/` (`server: cloudflare`), so paper copies already survive the flip at the cost of one redirect per scan. Operator step 5 re-checks it after SITE-Z deploys. Internal paths in this plan are slashless (`/petitions/{slug}/flyer`); the render script serves `/x` and `/x/` alike. After SITE-Z lands, the manifest's stored URL stays valid and nothing needs rerunning |
| A11 | Where `check:flyers` runs. The pre-commit hook runs `inv check` on every commit, so putting the check there would block any commit that touches a petition's Markdown (a one-word fix included) until Chromium has rendered a new PDF. Brandon chose a check that "warns"; the plan therefore runs `check:flyers` in `npm run check`, `ci.yml` and `deploy.yml` (a stale flyer can be committed, never shipped) and leaves `inv check` alone. Brandon may move it into `inv check` if he prefers the hard stop |
| A12 | QR decode gate. A Playwright e2e test, `tests/e2e/petition-qr.spec.ts`, screenshots the `.petition-qr__tile` element on the petition page at 1280px and 768px (both above the 640px hide point) and on the flyer page, decodes each with `zxing-wasm` 2.x (devDependency; `readBarcodes` takes the PNG bytes directly; the `.wasm` is read from `node_modules`, since the package otherwise fetches it from jsDelivr, and no network is touched) and asserts the text equals `petitionUrl(slug)`. The two page tests skip themselves when the built page says the petition is closed (A4 hides the tile), so a closure cannot block deploys; the flyer test always runs. It runs with the other specs (`npm run test:e2e`; ci.yml's `e2e` job on pull requests and, through deploy.yml's `workflow_call`, on every push to main) in the site's default dark theme. It is the gate for any later change to `QR_LOGO_FRACTION` or the overlay |
| A13 | Flyer fonts. Only the site's shipped OFL fonts appear inside `.flyer`: Space Grotesk 400 (flyer.astro imports `@fontsource/space-grotesk/400.css`) for prose, statement and byline, Space Grotesk 600 (loaded by Base) for title, labels and URL, Orbitron 700 for the wordmark. No Georgia, no `system-ui`, no `--font-mono`, no fallback list, so a missing face fails the `pdffonts` gate instead of substituting. This is a deliberate deviation from the site's serif heading face: the flyer is print, must render the same on every machine, and the committed PDF must not embed Apple or Microsoft system faces |
| A14 | Orphan flyers. Every file under `public/flyers/` must be `{slug}.pdf` or `{slug}.json` for a non-draft petition action that is open; anything else (renamed, drafted, deleted or closed petition) fails `check:flyers` with `orphan flyer public/flyers/{name}: delete it`. PDFs on GitHub Pages cannot be `noindex`ed, so deletion is the only control |
| A15 | Layout pins. Inside `.flyer` every size is `in` or `pt` (the root font size is 16, 18 or 20px per viewer, so rem would move the layout between machines); `.flyer` is `height: 11in` with no `overflow: hidden` (a spill must become page 2 so the render script refuses it); `print-color-adjust: exact`; the printed QR is 2.1in square with no CSS padding (scans from arm's length, about half a metre; never below 2in); the accent colour appears only on the two rules; the web tile is 8rem, bordered, no padding; the shrink order in § Design decides what gives when a petition spills |
| A16 | Render and check hardening. The route handler never calls `route.continue()` or `route.fallback()`; a request whose origin is not `http://flyer.local` gets 404 and is counted, and the script exits 1 if the count is non-zero; same-origin paths are `decodeURIComponent`ed, resolved with `path.resolve(dir, '.' + p)` and 404ed unless the result starts with `dir + sep`; the context has `serviceWorkers: 'block'` and `chromium.launch()` takes no `args`. The flyer HTML may contain none of `<form`, `data-names`, `petition-roll`, `data-count`, `api.dangerousrobot.org`, `challenges.cloudflare.com`. The script fails if the PDF bytes contain `os.hostname()`, `os.userInfo().username` or `os.homedir()`; `pdfinfo` must show the page title, no Author and 1 page; the Invoke task runs the script with `TZ=UTC`. `npm audit --omit=dev` runs after each runtime install; an accepted advisory gets a row in `docs/UNSCHEDULED.md` § Security follow-ups. The deploy.yml step has no `env:` block and sits before `rm -rf dist/admin`; zizmor runs before and after with the exact command in T6 step 7 |
| A17 | Slug rule. `listPetitionActions` throws on a file name that fails `/^[a-z0-9]+(-[a-z0-9]+)*$/` and on a front matter `slug` key (Astro's glob loader would route the page under that id instead of the file name, breaking A7); `petitionUrl` applies the same regex. `qrSvg` XML-escapes the `<title>` text (`set:html` is the only unescaped sink this plan adds) |
| A18 | Verification details. `qrSvg` returns the SVG without `qrcode`'s trailing newline, so the figure stays on one line of built HTML and the plan's `grep -c` counts hold; the T1 coverage assertion divides by the module count (`n - 8`) and is a sanity bound, the e2e decode being the real gate; the test's white rect is the literal `#fff`; the render script answers files with `route.fulfill({ path })` (Playwright infers the content type); Operator step 2 (Chromium install) is a precondition of T4 step 5 and T5 step 4; the expected failure message in T1 step 3 and T2 step 2 is the ESM form |

## Design

**Page.** `/petitions/{slug}` gains, at the end of the sign block's tally column (after the status chip, `margin-top: var(--space-lg)`, left edge aligned with the count), a `<figure class="petition-qr">` holding the QR SVG in a tile and one caption sentence. The tile is 8rem square, no padding (the SVG's own 4-module quiet zone and white background are the tile; module about 2.5 CSS px at the default 18px root), `background: #fff`, `border: 1px solid var(--color-border)` (the high-contrast themes already darken that token), `border-radius: var(--radius-sm)`; the code stays black on white and the logo black in every theme, with no theme filter (the nav's dark-mode invert is scoped to `.site-logo` and does not reach the SVG `<image>`). The caption is one sentence in `var(--font-size-sm)`, `var(--color-text-muted)`, `text-wrap: pretty`: "Scan to open this page on a phone, or print a flyer (PDF)." where "print a flyer (PDF)" (`FLYER_LINK_TEXT`) is the link to `/flyers/{slug}.pdf`, present only when that PDF exists in `public/flyers/` at build time; without it the sentence ends after "phone." No URL line on the page. Below 640px (the sign block's own breakpoint) the tile and the scan clause are hidden and only the flyer link line remains, capitalised with `::first-letter`; with no PDF the whole figure is hidden there (`data-flyer` attribute set only when `flyerHref` is passed). Figure and link are absent when the petition is closed (A4).

**Flyer page.** `/petitions/{slug}/flyer` renders with `Base` (`chrome="minimal"`, `layout="bare"`, `noindex`), excluded from the sitemap; Base's footer and accessibility control are hidden. Root `<div class="flyer" data-theme="light">`, `background: #fff; color: var(--color-text); print-color-adjust: exact; -webkit-print-color-adjust: exact`. Absolute units only inside `.flyer` (in and pt; no rem tokens): `@page { size: 8.5in 11in; margin: 0 }`; `.flyer { width: 8.5in; height: 11in; padding: 0.65in 0.65in 0.55in; display: flex; flex-direction: column; font: 400 10pt/1.4 "Space Grotesk" }`, children `flex: none`, no `overflow: hidden`. Global `h1`, `h2`, `h3`, `blockquote` and `p` rules (Georgia, rem sizes) are overridden inside `.flyer` with the faces and pt sizes below. Faces (A13): Space Grotesk 400 for prose, statement and byline; Space Grotesk 600 for title, label, "Sign the pledge" and URL; Orbitron 700 for the wordmark; nothing else. Colour: the accent only on the two 2px rules; all other text `var(--color-text)`, byline and "Scan the code or go to" `var(--color-text-muted)`; never `--color-text-faint`; QR pure `#000` on `#fff`; the page must read on a black-and-white photocopy. Top to bottom:

- Title: Space Grotesk 600, 28pt, line-height 1.1, letter-spacing 0.01em, `text-wrap: balance` (two balanced lines for the current title), margin 0 0 0.1in.
- Byline, as the page shows it (A5): Space Grotesk 400, 7.5pt, uppercase, letter-spacing 0.08em, muted, margin 0 0 0.25in.
- Statement (omitted when unset): `border-top: 2px solid var(--color-accent)`, padding-top 0.2in, Space Grotesk 400 italic (synthesised oblique: the family ships no italic; Q2), 17pt, line-height 1.3, max-width 6.3in, margin 0 0 0.3in.
- Definitions (`<Content />`): `columns: 2; column-gap: 0.4in; column-fill: balance`; the Markdown's `<h3><strong>Definitions</strong></h3>` becomes a label spanning both columns (`column-span: all`, Space Grotesk 600 10.5pt uppercase, letter-spacing 0.04em, `strong { font-weight: inherit }`, margin 0 0 0.12in); paragraphs 10pt/1.4, `break-inside: avoid`, margin 0 0 0.1in; the last paragraph (today "Please consider adding yourself as a signatory.") spans both columns in Space Grotesk 400 12pt, margin-top 0.12in, as the lead-in to the sign band.
- Sign band: `margin-top: auto` (takes the slack, so nothing pools mid-page), `border-top: 2px solid var(--color-accent)`, padding-top 0.2in, grid `2.1in 1fr`, column-gap 0.4in, `align-items: center`. Left: `<PetitionQr size="flyer">`, the SVG at 2.1in square, no padding or border (quiet zone inside; module about 0.94mm). Right: "Sign the pledge" Space Grotesk 600 18pt, margin 0 0 0.06in; "Scan the code or go to" Space Grotesk 400 11.5pt muted, margin 0 0 0.08in; the URL in Space Grotesk 600 13pt, black, as two block spans, host (`dangerousrobot.org`) then path (`/petitions/{slug}`), `overflow-wrap: normal` (the path sets about 3.9in and fits the 4.4in column).
- Issuer row: margin-top 0.25in, `border-top: 1px solid var(--color-border)`, padding-top 0.12in, flex, `align-items: center`, gap 0.12in: `dr-logo.png` at 0.38in, then "Dangerous Robot" in Orbitron 700 10pt, letter-spacing 0.03em (lift of `.site-name` without its accent left bar: the accent appears only on the two rules, A15). Nothing else on the row (Decision 4 fixes the content).

Budget: about 9.5in of the 9.8in available for the current petition (estimated at 9.35in for a serif; Space Grotesk at 10pt sets a touch wider), so the one-page check has a little slack. If a petition spills, shrink in this order: paragraph margins, body 10 → 9.5pt, statement 17 → 16pt, title 28 → 26pt; never the QR below 2in. If more than 1in of slack remains, grow the QR to 2.4in first. On screen (`@media screen`) the sheet previews on a `#888` body with `margin: 2rem auto` and a soft shadow. The render script refuses a PDF with more than one page.

**Files under `public/flyers/`.** `{slug}.pdf` and `{slug}.json` (`{ "slug", "url", "fingerprint", "generated" }`), both committed. `inv flyers` regenerates every open published petition's pair and skips closed ones.

**Check.** `npm run check:flyers`, after `npm run build`, for every non-draft action with a `petition` field: if the built page's status chip says closed, the page must not link the PDF and `public/flyers/{slug}.pdf` and `.json` must be absent (message: delete them); otherwise the PDF exists, the manifest's fingerprint and URL match the current ones, `dist/petitions/{slug}/flyer/index.html` exists, contains the QR figure and none of the forbidden strings (A16), and `dist/petitions/{slug}/index.html` links the PDF. Then every file in `public/flyers/` must belong to an open, non-draft petition action (A14). Any failure names `inv flyers` or says what to delete.

## Global Constraints

- Node `>=22.12.0`; Astro `^7.3.8`; new dependencies `qrcode@^1.5.4` (runtime), `@types/qrcode@^1.5.5` (dev) and `zxing-wasm@^2.2.4` (dev, e2e only). No other new packages; `@fontsource/space-grotesk` is already installed and the flyer imports one more weight file from it. `qrcode` is CommonJS with no `exports` map: use `import QRCode from 'qrcode'` (default import), which works under the Astro build and `tsx --test`. Never import `pngjs` (a transitive dependency of `qrcode`): `zxing-wasm` decodes PNG bytes itself.
- `src/lib/petition.ts` ships to the browser and must stay free of Node APIs; the new helpers go in their own files.
- Site unit tests use `node:test` via `npm run test:site` (`src/lib/**/*.test.ts`); e2e tests use `npm run test:e2e` (Playwright, builds the site into `node_modules/.cache/watch-e2e/<port>/dist` and previews it on port 4329).
- The flyer page is `noindex` and out of the sitemap; `public/robots.txt` is unchanged.
- Copy: caption "Scan to open this page on a phone, or print a flyer (PDF)." with `FLYER_LINK_TEXT = 'print a flyer (PDF)'` (A6); "Sign the pledge"; "Scan the code or go to"; wordmark "Dangerous Robot".
- Fonts inside `.flyer`: Space Grotesk 400 and 600, Orbitron 700, nothing else (A13); the `pdffonts` gate in T5 step 4 enforces it.
- No `cd &&` in Invoke tasks or docs; `inv flyers` runs from the repo root and runs the render script with `TZ=UTC`.
- Commits: conventional commits; explicit paths only (peers may share the checkout); every commit message ends with the `Co-Authored-By` trailer the session requires. Each task's commit also stages `docs/plans/petition-qr-flyer.md` (ticked checklist) and `docs/v1.0.0-roadmap.md` (SITE-BC checklist), per AGENTS.md rule 4.
- The pre-commit hook runs `inv check` on every commit (`check:flyers` is not part of it, A11). Temporary edits made for a verification step (T3 step 5 stub, T5 step 7 spacer, T6 steps 2 to 5) must never be staged; revert them before committing.
- Code edits need the work item registered (done in T0; `python3 scripts/release-gate/work_item.py status` shows SITE-BC with this plan's path).
- Operator step 2 (Playwright's Chromium) must be done before T4 step 5 and T5 step 4; the agent checks and stops if it is not.

## Review Focus

1. The pledge text is edited and deployed without rerunning `inv flyers`: `check:flyers` must fail in CI with a message naming `inv flyers` (T6 step 2, which edits the Markdown, not the manifest).
2. A new petition is published before anyone renders its flyer: the page must show the QR code with no flyer link, and `check:flyers` must fail for the missing PDF (T3 step 4, T6 step 3).
3. A closed petition: the QR code and the flyer link disappear, the rest of the sign block is unchanged, `check:flyers` demands the flyer files be deleted and passes once they are, and a flyer file with no open petition fails as an orphan (T3 step 5, T6 steps 4 and 5); the e2e page tests skip rather than fail on a closed petition (T4 step 5).
4. The QR code actually decodes with the logo in place: the e2e test decodes the web tile at two widths and the flyer tile to the page URL in the default dark theme (T4 step 5), the committed PDF embeds only SpaceGrotesk and Orbitron faces and Brandon's phone scan passes before the PDF is committed (T5 step 4), and the flyer page prints light whatever the viewer's theme (T4 step 4).
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
- Consumes: `qrcode` (`QRCode.toString(text, { type: 'svg', errorCorrectionLevel: 'H' })` resolves to an SVG string ending in `</svg>\n`, with `viewBox="0 0 N N"`, N = modules plus the default 4-module margin on each side (57 for the current URL, a version 8 code), containing a background `<path fill="#ffffff">` and the dark-module `<path stroke="#000000">`; no `role`, `<title>` or `<rect>`).
- Produces: `export async function qrSvg(url: string): Promise<string>`; `export const QR_LOGO_HREF = '/dr-logo.png'`; `export const QR_LOGO_FRACTION = 0.14`. The returned SVG ends in `</svg>` (trailing newline trimmed, A18), has `role="img"`, an `<title>` "QR code for {url}" with `&`, `<`, `>` and `"` XML-escaped as its first child, `qrcode`'s background and module paths, then a white `<rect fill="#fff">` and an `<image href="/dr-logo.png">` centred, sized from `QR_LOGO_FRACTION` of the viewBox width (the rect 1.12 times the image).

- [x] **Step 1: Add the dependency and audit it**

```bash
npm install qrcode@^1.5.4
npm install --save-dev @types/qrcode@^1.5.5
npm audit --omit=dev
```

Expected from the audit: `found 0 vulnerabilities`. Record the audit line in the commit body; if an advisory is accepted instead, add a row to `docs/UNSCHEDULED.md` § Security follow-ups in the same commit (A16). The install adds a second `yargs` 15 tree used only by `qrcode`'s CLI; keep the caret, as every other entry does.

- [x] **Step 2: Write the failing tests**

```ts
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { qrSvg, QR_LOGO_FRACTION, QR_LOGO_HREF } from './qr';

const URL = 'https://dangerousrobot.org/petitions/prohibit-ai-self-improvement';

describe('qrSvg', () => {
  test('is one svg with a title naming the url and no trailing newline', async () => {
    const svg = await qrSvg(URL);
    assert.match(svg, /^<svg[^>]*role="img"/);
    assert.match(svg, new RegExp(`<title>QR code for ${URL}</title>`));
    assert.ok(svg.endsWith('</svg>'), 'trimmed, so the figure stays on one line of built HTML');
  });
  test('escapes the title text', async () => {
    const svg = await qrSvg('https://dangerousrobot.org/p?a=1&b=2');
    assert.match(svg, /<title>QR code for https:\/\/dangerousrobot\.org\/p\?a=1&amp;b=2<\/title>/);
  });
  test('centres the logo on a white square at QR_LOGO_FRACTION', async () => {
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
    const modules = n - 8; // viewBox minus the 4-module quiet zone on each side
    assert.ok((w * 1.12) ** 2 / modules ** 2 < 0.3, 'sanity bound only: the e2e decode test is the real gate (A12)');
  });
  test('refuses a non-https url', async () => {
    await assert.rejects(qrSvg('javascript:alert(1)'));
  });
});
```

- [x] **Step 3: Run the tests to verify they fail**

Run: `npm run test:site`
Expected: FAIL, `Error [ERR_MODULE_NOT_FOUND]: Cannot find module '<repo>/src/lib/qr' imported from <repo>/src/lib/qr.test.ts`.

- [x] **Step 4: Implement `qrSvg(url: string): Promise<string>` in `src/lib/qr.ts`**

Validate with `new URL(url)` and throw when `protocol` is not `https:`; insert the string as passed (not `.href`) into the title after XML-escaping `&`, `<`, `>` and `"`. Trim the trailing newline from the string `qrcode` returns. Write the `<image>` attributes in the order `href`, `width`, `height`, `x`, `y`, as the test reads them; the rect's fill is the literal `#fff` (`#ffffff` fails the test). Insert the rect and image before the closing `</svg>`, and add `role="img"` and the `<title>` to the opening tag and as its first child.

- [x] **Step 5: Run the tests to verify they pass**

Run: `npm run test:site`
Expected: PASS, four `qrSvg` tests.

- [x] **Step 6: Commit**

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
  - `export const FLYER_LINK_TEXT = 'print a flyer (PDF)'`
  - `export const FLYERS_DIR = 'public/flyers'`
  - `export const FLYER_TEMPLATE_FILES = ['src/pages/petitions/[slug]/flyer.astro', 'src/components/PetitionQr.astro', 'src/lib/qr.ts']`
  - `export const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/`
  - `export function petitionUrl(slug: string): string` (`https://dangerousrobot.org/petitions/${slug}`, A10; throws when `slug` fails `SLUG_RE`. Lives here, not in `src/lib/actions.ts`, because that file imports `astro:content`, which scripts cannot load; the page and the scripts share this one function so the URL cannot drift)
  - `export const flyerPdfPath = (slug: string): string => \`/flyers/${slug}.pdf\`` (site path)
  - `export const flyerPagePath = (slug: string): string => \`/petitions/${slug}/flyer\``
  - `export interface FlyerManifest { slug: string; url: string; fingerprint: string; generated: string }`
  - `export interface PetitionAction { slug: string; draft: boolean; text: string }` (`text` is the whole file's contents)
  - `export function listPetitionActions(actionsDir = 'src/content/actions'): PetitionAction[]` (every `*.md` whose front matter has a `petition` key; `slug` is the file name without `.md`; `draft` from front matter, default false; throws naming the file when the name fails `SLUG_RE` or the front matter has a `slug` key, A17)
  - `export function flyerFingerprint(text: string, url: string, templateFiles: string[] = FLYER_TEMPLATE_FILES): string` (sha256 hex over `text`, `url` and each template file's contents, joined with `\0`; a template file that does not exist contributes an empty string)
  - `export function flyerState(slug: string, fingerprint: string, flyersDir = FLYERS_DIR): 'missing' | 'stale' | 'current'` (`missing` when the PDF or manifest is absent; `stale` when the manifest's fingerprint differs)
  - `export function writeFlyerManifest(manifest: FlyerManifest, flyersDir = FLYERS_DIR): void` (writes `{slug}.json`, two-space indented, trailing newline)
  - `export function pdfPageCount(pdf: Buffer): number` (count of `/Type /Page` objects that are not `/Pages`; Chromium writes these headers uncompressed; regex `/\/Type\s*\/Page(?![s\w])/g`)

- [x] **Step 1: Write the failing tests**

```ts
import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { listPetitionActions, flyerFingerprint, flyerState, writeFlyerManifest, pdfPageCount, flyerPdfPath, flyerPagePath, petitionUrl } from './flyer';

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
  test('listPetitionActions rejects a bad file name and a front matter slug', () => {
    writeFileSync(join(actions, 'Bad_Name.md'), '---\ntitle: B\npetition: z\n---\n');
    assert.throws(() => listPetitionActions(actions), /Bad_Name\.md/);
    rmSync(join(actions, 'Bad_Name.md'));
    writeFileSync(join(actions, 'aliased.md'), '---\ntitle: A\npetition: z\nslug: other\n---\n');
    assert.throws(() => listPetitionActions(actions), /aliased\.md/);
  });
  test('petitionUrl builds the slashless page url and rejects a bad slug', () => {
    assert.equal(petitionUrl('p'), 'https://dangerousrobot.org/petitions/p');
    assert.throws(() => petitionUrl('../x'));
    assert.throws(() => petitionUrl('Upper'));
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

- [x] **Step 2: Run the tests to verify they fail**

Run: `npm run test:site`
Expected: FAIL, `Error [ERR_MODULE_NOT_FOUND]: Cannot find module '<repo>/src/lib/flyer' imported from <repo>/src/lib/flyer.test.ts`.

- [x] **Step 3: Implement the functions above in `src/lib/flyer.ts`**

Front matter: the text between the first two `---` lines, parsed with `js-yaml` `load`; a file without a block or without `petition` is skipped. The file-name and `slug`-key checks apply only to files that pass the `petition`-key filter; a badly named file without `petition` is skipped like any other.

- [x] **Step 4: Run the tests to verify they pass**

Run: `npm run test:site`
Expected: PASS, seven `flyer helpers` tests.

- [x] **Step 5: Commit**

```bash
git add src/lib/flyer.ts src/lib/flyer.test.ts docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(site): flyer path, fingerprint and manifest helpers (SITE-BC)"
```

### T3: `PetitionQr` component in the sign block

**Files:**
- Create: `src/components/PetitionQr.astro`
- Modify: `src/components/PetitionSign.astro` (props, tally column markup), `src/pages/petitions/[slug].astro` (pass `pageUrl` and `flyerHref`)

**Interfaces:**
- Consumes: `qrSvg` (T1); `flyerPdfPath`, `petitionUrl`, `FLYER_LINK_TEXT`, `FLYERS_DIR` (T2).
- Produces: `PetitionQr.astro` with `interface Props { url: string; flyerHref?: string; size?: 'page' | 'flyer' }` (default `page`) rendering `<figure class="petition-qr" data-size={size} data-flyer={flyerHref ? '' : undefined}>` containing `<div class="petition-qr__tile">` with the SVG (`set:html`) and, for `size="page"` only, `<figcaption class="petition-qr__caption"><span class="petition-qr__scan">Scan to open this page on a phone{flyerHref ? ', or ' : '.'}</span>{flyerHref && <><a href={flyerHref}>{FLYER_LINK_TEXT}</a>.</>}</figcaption>` (no `download` attribute: the browser's PDF viewer has Print one click away). `size="flyer"` renders the tile alone. `PetitionSign.astro` gains props `pageUrl: string` and `flyerHref?: string` and renders `<PetitionQr>` at the end of `.petition-tally`, wrapped in `{!closed && (...)}`. The page computes `pageUrl = petitionUrl(action.id)` (A10).

- [x] **Step 1: Take the baseline**

There is no component test runner; the check is the built HTML (T6's `check-flyers.ts` makes it permanent, T4 step 5's e2e test decodes it). Build and grep:

Run: `npm run build && grep -c 'class="petition-qr' dist/petitions/prohibit-ai-self-improvement/index.html`
Expected before the change: `0`.

- [x] **Step 2: Create `PetitionQr.astro`**

Styles (scoped), per § Design Page: `.petition-qr { display: grid; gap: var(--space-xs); justify-items: start; margin: var(--space-lg) 0 0; }`; `.petition-qr__tile { width: 8rem; height: 8rem; padding: 0; box-sizing: border-box; background: #fff; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }` with the SVG filling it (`svg { display: block; width: 100%; height: 100%; }`); `.petition-qr__caption { margin: 0; font-size: var(--font-size-sm); color: var(--color-text-muted); text-wrap: pretty; }` with the link in the site's default link style; `@media (max-width: 640px) { .petition-qr:not([data-flyer]) { display: none; } .petition-qr__tile, .petition-qr__scan { display: none; } .petition-qr__caption::first-letter { text-transform: uppercase; } }`; `[data-size="flyer"] { margin: 0; gap: 0; } [data-size="flyer"] .petition-qr__tile { width: 2.1in; height: 2.1in; border: 0; border-radius: 0; }`. No padding anywhere: the SVG's own quiet zone is the margin. No theme filter on the SVG or its `<image>`.

- [x] **Step 3: Wire it into the sign block and the page**

In `[slug].astro`: `const pageUrl = petitionUrl(action.id);` and `const flyerHref = existsSync(join(FLYERS_DIR, \`${action.id}.pdf\`)) ? flyerPdfPath(action.id) : undefined;` passed to `<PetitionSign>` (`petitionUrl` throws on a bad id, so the lookup cannot leave `public/flyers/`). In `PetitionSign.astro`: render `{!closed && <PetitionQr url={pageUrl} flyerHref={flyerHref} />}` after `.petition-tally__status`. The sign block's 640px breakpoint stacks the board into one column already; the component's own 640px rule hides the tile there. Nothing else changes.

- [x] **Step 4: Build and verify**

Run: `npm run build && grep -c 'class="petition-qr' dist/petitions/prohibit-ai-self-improvement/index.html && grep -c 'print a flyer' dist/petitions/prohibit-ai-self-improvement/index.html`
Expected: `1` then `0` (the figure is one line because `qrSvg` is trimmed; no PDF exists yet, so no link: Review Focus 2). Also `npm run check:types` passes.

- [x] **Step 5: Hidden when closed**

Temporarily point `PUBLIC_PETITION_API` at a local stub that returns `{"status":"closed","closed_at":"2026-10-01T00:00:00Z","count":3,"names":[]}` (for example `python3 -m http.server` in a scratchpad folder serving a `petitions/prohibit-ai-self-improvement` file), build, and confirm `grep -c 'class="petition-qr' dist/petitions/prohibit-ai-self-improvement/index.html` prints `0`. Record the result in the commit message body. Nothing from the stub is staged.

- [x] **Step 6: Screenshot in light and dark mode**

With `inv dev` on port 4321, take `/petitions/prohibit-ai-self-improvement#sign` at 1200px and 400px widths, light and dark (`document.documentElement.dataset.theme = 'dark'`). Check at 1200px: the tile is white with a visible border in light mode and white on the dark surface in dark mode, the logo black, the tile's left edge aligned with the count, the caption reads "Scan to open this page on a phone." (no link yet). Check at 400px: no tile, no caption, no figure at all (no PDF yet, so `data-flyer` is absent), and no horizontal overflow. Keep the screenshots under the scratchpad and name them in the handoff note.

- [x] **Step 7: Commit**

```bash
git add src/components/PetitionQr.astro src/components/PetitionSign.astro src/pages/petitions/[slug].astro docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(site): QR code beside the petition tally (SITE-BC)"
```

### T4: Flyer page route, out of the sitemap; QR decode e2e test

**Files:**
- Create: `src/pages/petitions/[slug]/flyer.astro`, `tests/e2e/petition-qr.spec.ts`
- Modify: `astro.config.ts` (sitemap `filter`), `package.json` (devDependency `zxing-wasm`), `package-lock.json`

**Interfaces:**
- Consumes: `getActions` (`src/lib/actions.ts`); `petitionUrl` (T2); `render` from `astro:content`; `PetitionQr` (T3) with `size="flyer"`; `formatPostDate` (`src/lib/writing.ts`); `Base`; `@fontsource/space-grotesk/400.css`.
- Produces: the route `/petitions/{slug}/flyer` (built as `dist/petitions/{slug}/flyer/index.html`) for every action with a `petition` field (drafts included in dev, dropped in production, as `getActions` does). Root element `<div class="flyer" data-theme="light">`. The e2e spec `tests/e2e/petition-qr.spec.ts` (A12): three tests, page tile at 1280px and 768px and the flyer tile, each decoded to `petitionUrl('prohibit-ai-self-improvement')`.

- [x] **Step 1: Create the page**

`getStaticPaths` mirrors `[slug].astro`. `import '@fontsource/space-grotesk/400.css'` in the frontmatter. `<Base title={\`${title} flyer\`} description={description} layout="bare" chrome="minimal" noindex>`. Markup, top to bottom: `<h1 class="flyer__title">` title; `<p class="flyer__byline">` "Written by {author}{ai_assisted && ', with AI assistance'} · {formatPostDate(pubDate)}"; `<blockquote class="flyer__statement">` with `petition_statement` (omit the block when unset); `<div class="flyer__body"><Content /></div>`; `<footer class="flyer__sign">` with `<PetitionQr url={pageUrl} size="flyer" />` and a `<div>` holding `<h2>Sign the pledge</h2>`, `<p>Scan the code or go to</p>`, `<p class="flyer__url"><span>dangerousrobot.org</span><span>/petitions/{slug}</span></p>`; `<div class="flyer__issuer"><img src="/dr-logo.png" alt="" width="48" height="48"><span class="flyer__wordmark">Dangerous Robot</span></div>`. Styles per § Design Flyer page: `@page`, the `.flyer` box in in/pt with `height: 11in` and no `overflow: hidden`, `print-color-adjust: exact`, the font-family overrides for `.flyer`, `.flyer h1`, `.flyer h2`, `.flyer h3`, `.flyer blockquote` and `.flyer p` (the global rules set Georgia and rem sizes), the two-column body, the sign band and issuer row, plus `@media screen { body { background: #888 } .flyer { margin: 2rem auto; box-shadow: 0 0 1rem rgb(0 0 0 / 0.3) } }` so the page previews as a sheet in a browser. Hide Base's footer and the accessibility control on this page: `:global(.a11y-root), :global(.site-footer) { display: none }`.

- [x] **Step 2: Exclude from the sitemap**

In `astro.config.ts`'s sitemap `filter`, as the first statement (before the `INDEX_ALPHA_DETAIL_PAGES` early return): `if (/\/flyer\/?$/.test(new URL(page).pathname)) return false;`. Sitemap entries have no trailing slash under `trailingSlash: "never"`, hence the optional slash.

- [x] **Step 3: Build and verify**

Run: `npm run build && test -f dist/petitions/prohibit-ai-self-improvement/flyer/index.html && grep -c -e '<form' -e data-names -e petition-roll -e data-count -e api.dangerousrobot.org -e challenges.cloudflare.com dist/petitions/prohibit-ai-self-improvement/flyer/index.html; grep -c 'noindex' dist/petitions/prohibit-ai-self-improvement/flyer/index.html; grep -c '/flyer<' dist/sitemap-0.xml; grep -c 'class="petition-qr__caption' dist/petitions/prohibit-ai-self-improvement/flyer/index.html`
Expected: `0`, `1`, `0`, `0` (no forbidden strings, one `noindex` meta, no sitemap entry, no caption on the flyer tile).

Control for the first zero (the same grep must find the strings where they do exist):

Run: `grep -c -e '<form' -e data-names -e petition-roll -e data-count -e api.dangerousrobot.org -e challenges.cloudflare.com dist/petitions/prohibit-ai-self-improvement/index.html`
Expected: `1` or more.

- [x] **Step 4: Preview as a sheet, in dark mode too**

Open `http://localhost:4321/petitions/prohibit-ai-self-improvement/flyer` in Chrome with the site theme set to dark, then File > Print preview, Letter, no margins: one page, white background, dark text, nothing clipped, Space Grotesk everywhere (no serif anywhere), accent colour only on the two rules, the QR at 2.1in with the logo in its centre, the URL on two lines with no mid-word break. If it spills, apply § Design's shrink order (paragraph margins, body 10 → 9.5pt, statement 17 → 16pt, title 28 → 26pt), never the QR. Screenshot to the scratchpad.

- [x] **Step 5: QR decode e2e test (A12)**

Precondition: Operator step 2 (Playwright's Chromium). Check first:

Run: `test -x "$(node -e "console.log(require('@playwright/test').chromium.executablePath())")" && echo chromium ok`
Expected: `chromium ok`. Nothing printed: stop and ask Brandon to run Operator step 2.

Install: `npm install --save-dev zxing-wasm@^2.2.4` (dev-only; no runtime audit change). Write `tests/e2e/petition-qr.spec.ts`:

```ts
// The QR code carries the DR logo over its centre; this is the gate that the
// result still decodes (A12). Imports test from @playwright/test, not
// ./helpers: the helpers' network fixture fails on any external request and
// the petition page asks for Turnstile and the petition API.
import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { prepareZXingModule, readBarcodes } from 'zxing-wasm/reader';
import { petitionUrl } from '../../src/lib/flyer';

const SLUG = 'prohibit-ai-self-improvement';
const EXPECTED = petitionUrl(SLUG);

// zxing-wasm fetches its binary from jsDelivr unless told otherwise; the
// suite stays offline by handing it the installed file (cwd is the repo root).
const wasm = readFileSync('node_modules/zxing-wasm/dist/reader/zxing_reader.wasm');
prepareZXingModule({ overrides: { wasmBinary: wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength) } });

async function decode(png: Buffer): Promise<string | undefined> {
  const [hit] = await readBarcodes(new Uint8Array(png), { formats: ['QRCode'], tryHarder: true });
  return hit?.text;
}

test.beforeEach(async ({ context, baseURL }) => {
  const local = new URL(baseURL ?? 'http://127.0.0.1').origin;
  await context.route((url) => url.origin !== local, (route) => route.abort('blockedbyclient'));
});

for (const width of [1280, 768]) {
  test(`the page QR decodes to the page URL at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/petitions/${SLUG}`);
    test.skip((await page.locator('[data-status="closed"]').count()) > 0, 'a closed petition shows no QR (A4)');
    await page.waitForLoadState('networkidle'); // the logo <image> must be painted
    const tile = page.locator('.petition-qr__tile');
    await expect(tile).toBeVisible();
    expect(await decode(await tile.screenshot())).toBe(EXPECTED);
  });
}

test('the flyer QR decodes to the page URL', async ({ page }) => {
  await page.goto(`/petitions/${SLUG}/flyer`);
  await page.waitForLoadState('networkidle');
  expect(await decode(await page.locator('.petition-qr__tile').screenshot())).toBe(EXPECTED);
});
```

Run: `npm run test:e2e -- petition-qr`
Expected: `3 passed` (the run builds the site into `node_modules/.cache/watch-e2e/4329/dist` first; allow a few minutes). A failure here means the overlay is unreadable: do not change `QR_LOGO_FRACTION` upward; raise it in the handoff note.

- [x] **Step 6: Commit**

```bash
git add src/pages/petitions/[slug]/flyer.astro astro.config.ts tests/e2e/petition-qr.spec.ts package.json package-lock.json docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(site): one-page flyer route per petition and QR decode e2e test (SITE-BC)"
```

### T5: `inv flyers` render task; first PDF committed

**Files:**
- Create: `scripts/render-flyers.ts`, `public/flyers/prohibit-ai-self-improvement.pdf`, `public/flyers/prohibit-ai-self-improvement.json`
- Modify: `tasks.py` (task `flyers`), `package.json` (`"flyers": "tsx scripts/render-flyers.ts"`)

**Interfaces:**
- Consumes: `chromium` from `@playwright/test`; `node:os`, `node:path`; `listPetitionActions`, `flyerPagePath`, `flyerFingerprint`, `writeFlyerManifest`, `pdfPageCount`, `petitionUrl`, `FLYERS_DIR` (T2).
- Produces: `scripts/render-flyers.ts --dist <dir>`: for each non-draft petition action, reads `<dir>/petitions/{slug}/index.html`; if it contains `data-status="closed"`, prints `skip {slug}: closed (A4)` and moves on. Otherwise opens `http://flyer.local{flyerPagePath(slug)}` in a fresh context from `chromium.launch()` with no `args` (`newContext({ colorScheme: 'light', serviceWorkers: 'block' })`), with every request answered by one `page.route('**/*', ...)` handler that never calls `route.continue()` or `route.fallback()`: a request whose `url.origin` is not `http://flyer.local` is fulfilled with `status: 404` and counted; a same-origin request has its `decodeURIComponent(pathname)` resolved with `path.resolve(dir, '.' + p)`, gets 404 unless the result starts with `dir + sep`, maps a directory (with or without a trailing slash) to its `index.html`, and is answered with `route.fulfill({ path })` for an existing file (Playwright infers the content type) or `status: 404`. The script waits for `document.fonts.ready`, then `page.pdf({ path: <tmp>, format: 'Letter', printBackground: true, preferCSSPageSize: true })` into a temporary file under `node_modules/.cache/flyers/`. Refusals, each leaving the committed files untouched and exiting 1: foreign-origin count above zero (`flyer for {slug} requested {n} foreign URL(s): {list}`); `pdfPageCount` not 1 (`flyer for {slug} runs to N pages: shorten the text or apply the shrink order in src/pages/petitions/[slug]/flyer.astro`); the PDF bytes containing `os.hostname()`, `os.userInfo().username` or `os.homedir()` (`flyer for {slug} embeds a machine name or path`). Otherwise move it to `public/flyers/{slug}.pdf`, write the manifest (`url: petitionUrl(slug)`, `fingerprint: flyerFingerprint(text, url)`, `generated` ISO date-time) and print both paths. On a Chromium launch failure, print `npx playwright install chromium`.

- [ ] **Step 1: Confirm Chromium is installed (Operator step 2)**

Run: `test -x "$(node -e "console.log(require('@playwright/test').chromium.executablePath())")" && echo chromium ok`
Expected: `chromium ok`. Nothing printed: stop and ask Brandon to run Operator step 2; nothing below works without it.

- [ ] **Step 2: Write `scripts/render-flyers.ts`**

Per the Produces block.

- [ ] **Step 3: Add the Invoke task and npm script**

`tasks.py`, next to `check`:

```python
@task
def flyers(ctx):
    """Render each open petition's one-page flyer PDF into public/flyers/ (commit the result)."""
    out = "node_modules/.cache/flyers/dist"
    ctx.run(f"npm run build -- --outDir {out}", pty=True)
    # UTC so the PDF's CreationDate carries no local timezone offset.
    ctx.run(f"npm run flyers -- --dist {out}", pty=True, env={"TZ": "UTC"})
```

Register it with `ns.add_task(flyers)`.

- [ ] **Step 4: Render the first flyer and gate it**

Run: `inv flyers`
Expected: prints `public/flyers/prohibit-ai-self-improvement.pdf` and `.json`. Open the PDF: one Letter page, logo visible in the QR's centre, URL on two lines matching the page. Then the gates:

Run: `pdfinfo public/flyers/prohibit-ai-self-improvement.pdf | grep -E '^(Title|Author|Pages|Page size):'`
Expected: `Title:          Prohibit AI Self-Improvement Pledge flyer - Dangerous Robot`, `Pages:          1`, `Page size:      612 x 792 pts (letter)`, and no `Author:` line (poppler is at `/opt/homebrew/bin`).

Run: `pdffonts public/flyers/prohibit-ai-self-improvement.pdf | tail -n +3 | grep -vc -e SpaceGrotesk -e Orbitron`
Expected: `0` (every embedded face is a SpaceGrotesk or Orbitron subset; any SFPro, Georgia, Helvetica or DejaVu line fails this step: fix the `.flyer` font rules, A13). Control: `pdffonts public/flyers/prohibit-ai-self-improvement.pdf | tail -n +3 | grep -c SpaceGrotesk` prints `2` or more (the 400 and 600 subsets).

Run: `grep -ac "$(whoami)" public/flyers/prohibit-ai-self-improvement.pdf; grep -ac Skia public/flyers/prohibit-ai-self-improvement.pdf`
Expected: `0` then `1` or more (the second line proves `grep -a` reads the PDF; the first is the manual control for the script's own byte scan).

Operator gate (Brandon): scan the PDF's QR from the screen and from a printed sheet at arm's length, about half a metre, with an iPhone and an Android phone where available; each must open the petition page. The agent pauses here and does not run step 8 until the handoff note says "scanned OK". A failed scan goes to Brandon with the e2e result (T4 step 5) attached; it is his call between a smaller logo and masking the eye (Q1).

- [ ] **Step 5: Confirm the page now links the PDF**

Run: `npm run build && grep -c 'href="/flyers/prohibit-ai-self-improvement.pdf"' dist/petitions/prohibit-ai-self-improvement/index.html && grep -c 'print a flyer (PDF)</a>.' dist/petitions/prohibit-ai-self-improvement/index.html`
Expected: `1` then `1`.

- [ ] **Step 6: Rerun is a no-op on the manifest fingerprint**

Run `inv flyers` again and `git diff --stat public/flyers/`: only `generated` changes in the JSON (the PDF bytes may differ by timestamp; that is fine).

- [ ] **Step 7: Refuses a second page**

Temporarily add `<p style="height: 6in"></p>` to the flyer body in `flyer.astro`, run `inv flyers`: exit code 1, the message names the slug and the file, and `git status public/flyers/` shows no change. Revert the temporary edit before committing.

- [ ] **Step 8: Commit**

```bash
git add scripts/render-flyers.ts tasks.py package.json public/flyers/prohibit-ai-self-improvement.pdf public/flyers/prohibit-ai-self-improvement.json docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "feat(ops): inv flyers renders the petition flyer PDF (SITE-BC)"
```

The commit body records the `pdfinfo` and `pdffonts` results and "scanned OK" with the phones used.

### T6: `check:flyers` in the check chain and both workflows

**Files:**
- Create: `scripts/check-flyers.ts`
- Modify: `package.json` (`check:flyers` script; append to `check`), `.github/workflows/ci.yml` and `.github/workflows/deploy.yml` (a `run: npm run check:flyers` step after `check:watch`). Not `tasks.py` `check` (A11)

**Interfaces:**
- Consumes: `listPetitionActions`, `flyerFingerprint`, `flyerState`, `flyerPdfPath`, `flyerPagePath`, `petitionUrl`, `FLYERS_DIR` (T2). Env `FLYER_CHECK_DIST` overrides `dist`, as `WATCH_CHECK_DIST` does.
- Produces: exit 1 with one line per failure. For each non-draft petition action, read `dist/petitions/{slug}/index.html`; if it contains `data-status="closed"`, require that it does not contain `href="{flyerPdfPath(slug)}"` and that `public/flyers/{slug}.pdf` and `.json` are absent (`closed petition {slug}: delete public/flyers/{slug}.pdf and public/flyers/{slug}.json (git history keeps them)`), then continue to the next action; otherwise require `flyerState(slug, flyerFingerprint(text, petitionUrl(slug)))` is `current` (report `missing` or `stale`, ending "run `inv flyers` and commit public/flyers/"), the manifest's `url` equals `petitionUrl(slug)`, `dist/petitions/{slug}/flyer/index.html` exists, contains `class="petition-qr` and none of `<form`, `data-names`, `petition-roll`, `data-count`, `api.dangerousrobot.org`, `challenges.cloudflare.com` (A16), and the petition page contains `href="{flyerPdfPath(slug)}"`. Then every entry of `public/flyers/` must be `{slug}.pdf` or `{slug}.json` for an open action checked above; anything else fails `orphan flyer public/flyers/{name}: delete it` (A14). Exit 0 prints "flyers: N petition(s) current, M closed".

- [ ] **Step 1: Write the script**

Same shape as `scripts/check-watch-page.ts`: collect `errors`, print, exit.

- [ ] **Step 2: Prove it fails on a stale flyer (Review Focus 1)**

Run `npm run build` once. Append one line to `src/content/actions/prohibit-ai-self-improvement.md`, run `npm run check:flyers`: exit 1, the message says `stale` and names `inv flyers`. Restore the file with `git checkout -- src/content/actions/prohibit-ai-self-improvement.md`.

- [ ] **Step 3: Prove it fails on a missing PDF (Review Focus 2)**

Move the PDF aside, run `npm run check:flyers`: exit 1, `missing`. Move it back.

- [ ] **Step 4: Prove a closed petition demands deletion, then passes (Review Focus 3)**

With the closed stub from T3 step 5, build, run `npm run check:flyers`: exit 1, `closed petition prohibit-ai-self-improvement: delete public/flyers/...`. Move both flyer files to the scratchpad, run again: exit 0, `flyers: 0 petition(s) current, 1 closed`. Move them back, rebuild without the stub.

- [ ] **Step 5: Prove an orphan fails (A14)**

Run: `cp public/flyers/prohibit-ai-self-improvement.json public/flyers/nope.json && npm run check:flyers; rm public/flyers/nope.json`
Expected: exit 1 with `orphan flyer public/flyers/nope.json: delete it`.

- [ ] **Step 6: Prove it passes**

Run: `npm run check:flyers`
Expected: `flyers: 1 petition(s) current, 0 closed`, exit 0.

- [ ] **Step 7: Wire it in**

Before editing, copy the current workflows to `<scratchpad>/zizmor-head/.github/workflows/` and run the control: `uvx zizmor --no-progress --format plain --min-severity low <scratchpad>/zizmor-head/.github/workflows`. Then: `package.json` `check` chain gets `&& npm run check:flyers` after `check:watch`; `ci.yml`'s `check` job gets `- run: npm run check:flyers` after its `check:watch` step; `deploy.yml` gets the same step after its `check:watch` step, with no `env:` block (the neighbouring `check:watch` step carries `YOUTUBE_API_KEY`; do not copy it) and before `rm -rf dist/admin` and `upload-pages-artifact`; `inv check` is left as is (A11).

Run: `uvx zizmor --no-progress --format plain --min-severity low .github/workflows`
Expected: the same finding list as the control run (the pre-existing `unpinned-uses` findings belong to the SHA-pinning row in `docs/UNSCHEDULED.md`, not to this item); no new finding.

- [ ] **Step 8: Commit**

```bash
git add scripts/check-flyers.ts package.json .github/workflows/ci.yml .github/workflows/deploy.yml docs/plans/petition-qr-flyer.md docs/v1.0.0-roadmap.md
git commit -m "ci: check:flyers fails when a petition flyer is missing, stale or orphaned (SITE-BC)"
```

### T7: Docs, backlog, finish

**Files:**
- Modify: `docs/architecture/petitions.md` (Pieces table: QR component, flyer page, `public/flyers/`, render and check scripts, the decode e2e test; Routes: the flyer page), `docs/architecture/site.md` (the `npm run check` chain and CI step lists; the e2e spec list), `docs/runbook.md` ("Petitions" section: a "Flyer" paragraph: when to run `inv flyers`, commit `public/flyers/`, that `check:flyers` blocks a stale deploy, that a closed petition's flyer files must be deleted, the phone-scan check after a rerun, and that `QR_LOGO_FRACTION` changes only with the e2e decode test passing), `docs/UNSCHEDULED.md` (record any follow-up that came up during T1 to T6, with a triage marker; if none, no change, and say so in the commit body), `docs/v1.0.0-roadmap.md` (SITE-BC checklist, status `done` with commit refs), this plan (status checklist, Status line).

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

## Open questions for Brandon

- Q1 (logo size versus eye mask): the plan ships the logo at 14% of the code (A1), which decoded in every test. The alternative is 22% with the robot's eye masked by a white circle in the overlay, which also decoded; that changes the mark, so it is not a task here. Either way the e2e decode test (A12) is the gate.
- Q2 (statement italic or upright): `PetitionSign.astro`'s comment says "Upright, not italic: the statement is a declaration" and its style sets `font-style: italic`. The flyer keeps italic to match what renders today (as a synthesised oblique, since Space Grotesk has no italic face). Say which you want and both get the same treatment.

## Operator steps (Brandon)

1. Review this plan; T0 promotes it.
2. `npx playwright install chromium` once, if the e2e tests have never run on this machine. T4 step 5 and T5 step 4 check for it and stop if it is missing.
3. After T3 lands: scan the QR code on the dev page with a phone, in dark mode too. Inside T5 step 4: scan the PDF's QR code from the screen and from a printed sheet at arm's length (about half a metre), with an iPhone and an Android phone where available; write "scanned OK" and the phones used in the handoff note. The agent waits for that line before committing the PDF.
4. Push and deploy as usual; the Worker is untouched.
5. After SITE-Z (Trailing-slash URLs) deploys: `curl -sI https://dangerousrobot.org/petitions/prohibit-ai-self-improvement | head -3` must still show the 301 to the slash form observed on 2026-10-18 (A10). If it does not, rerun `inv flyers` with `petitionUrl` changed to the slash form and reprint.

## Self-review (agent, 2026-10-18)

- Spec coverage: QR with logo (T1, T3), near the sign form (T3), PDF without the form and with the QR (T4, T5), linked with a "print a flyer (PDF)" caption (T3), committed script output (T5), staleness check (T6), US Letter (T4, T5), plain URL (T2, T3, T5). No gap found.
- Names used across tasks: `qrSvg`, `QR_LOGO_HREF`, `QR_LOGO_FRACTION` (T1 → T3); `flyerPdfPath`, `flyerPagePath`, `FLYER_LINK_TEXT`, `FLYERS_DIR`, `FLYER_TEMPLATE_FILES`, `SLUG_RE`, `petitionUrl`, `listPetitionActions` (`text`), `flyerFingerprint`, `flyerState`, `writeFlyerManifest`, `pdfPageCount` (T2 → T3, T4, T5, T6). Consistent.
- Review Focus 1 to 5 each have a step: T6 step 2; T3 step 4 with T6 step 3; T3 step 5 with T6 steps 4 and 5; T4 steps 4 and 5 with T5 step 4; T5 step 7.

## Review history

| Date | Reviewer | Scope | Outcome |
|---|---|---|---|
| 2026-10-18 | agent (claude-opus-5-5), fresh-eyes builder check against the repo | full | iterated: fixed the sitemap filter for `trailingSlash: "never"`, settled the URL form against SITE-Z (A10), made a closed petition pass `check:flyers` (A4), renamed `source` to `text` and made the stale test edit the Markdown, widened the fingerprint to the templates and URL (A8), temp-file render, light colour scheme and hidden a11y control on the flyer, plan and roadmap staged in every commit, T0 promotion step, UNSCHEDULED.md step |
| 2026-10-18 | Brandon | full | approved as is, default answers to the four open calls (A11 check placement, A4 closed petition, A10 URL form, A8 fingerprint scope); promoted to `docs/plans/` |
| 2026-10-18 | agent (claude-fable-5-1), layout reviewer | full | iterated: absolute units and fixed height on the flyer, 2.1in printed QR, 8rem bordered web tile, one caption sentence and no URL line on the page, tile hidden below 640px, flyer composition with sign band, issuer row and shrink order, greyscale rules (A3, A15; § Design replaced) |
| 2026-10-18 | agent (claude-fable-5-1), security reviewer | full | iterated: XML-escaped title and slug rule (A17), shipped-fonts-only flyer with a `pdffonts` gate (A13), locked-down route handler, forbidden strings in the flyer HTML, `pdfinfo` and byte scan, `TZ=UTC`, `npm audit --omit=dev`, workflow step placement and zizmor command (A16), closed petitions delete their files and orphan flyers fail (A4, A14) |
| 2026-10-18 | agent (claude-fable-5-1), accuracy reviewer | full | iterated: logo fraction 0.22 → 0.14 after the 22% overlay failed to decode (A1), e2e decode gate (A12), A10 rewritten as observed (live 301), trimmed `qrSvg` so `grep -c` holds, coverage assertion over the module count, `#fff` literal, `route.fulfill({ path })`, Chromium install as a precondition, ESM error wording (A18), phone scan moved before the PDF commit |
| 2026-10-18 | agent (claude-fable-5-1), editor | full | folded the three reports into the plan: calls A12 to A18 added, A1, A3, A4, A6, A10 rewritten, `petitionUrl` moved to T2, e2e test added to T4, T5 and T6 gates and steps rewritten, Open questions section added (Q1 eye mask, Q2 statement italic) |

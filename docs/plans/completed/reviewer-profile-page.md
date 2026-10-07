# Reviewer profile page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status**: done (roadmap item SITE-N (Reviewer profile page), later beta)

**Goal:** Every page that names the claim reviewer shows the reviewer's handle, linked to a new profile page at `/people/<handle>` that carries the full name, bio, disclosure and the list of claims they reviewed.

**Architecture:** `src/lib/reviewers.ts` becomes the one place that knows a person: handle, full name, and which raw reviewer values (audit sidecar emails) map to them. Claim pages and the other reviewer mentions read the handle and profile link from it. One static page per person under `src/pages/people/` holds the bio prose and builds the claim list from the `claims` collection. A build-output check, part of `npm run check`, fails if a reviewer mention prints the full name, a reviewed claim page lacks the profile link, or a profile page is missing.

**Tech Stack:** Astro 6, TypeScript, `tsx` for the check script (same pattern as `scripts/check-citations.ts`).

**Spec:** this file (§ Design). Settled with the operator 2026-10-07: later beta; `/people/<handle>`; the operator's handle is `brandon-f`; reviewer display text is the handle; the profile shows full name, bio and claims; every reviewer mention changes, not only claim pages; the Values signature keeps the full name and links the profile.

## Design

| Where | Today | After |
|---|---|---|
| Claim page header (`src/pages/research/claims/[...slug].astro:127-129`) | Reviewed and approved by Brandon Faloona → `/about#who-runs-this` | Reviewed and approved by brandon-f → `/people/brandon-f` |
| Claim page audit trail (`[...slug].astro:244`) | Reviewed {date} by Brandon Faloona (no link) | Reviewed {date} by brandon-f (linked to the profile) |
| Research index, "What is this site?" (`src/pages/research/index.astro:161`) and its FAQ JSON-LD text (`:26`) | Brandon Faloona reviews and approves every published claim. | brandon-f reviews and approves every published claim. (linked in the HTML; plain text in JSON-LD) |
| Research index, conflicts of interest (`index.astro:369`) and its JSON-LD text (`:82`) | Dangerous Robot is run by Brandon Faloona (→ `/about#who-runs-this`) | Dangerous Robot is run by brandon-f (→ profile) |
| Corrections (`src/pages/corrections.astro:28`) | Brandon Faloona reviews every report. | brandon-f reviews every report. (linked) |
| About, "Who runs this" (`src/pages/about.astro:44-49`) | Full-name bio and TreadLightlyAI disclosure | Same text with the handle, linked to the profile; the disclosure stays here too |
| Values signature (`src/pages/values.astro:68`) | Brandon Faloona → `/about#who-runs-this` | Brandon Faloona → `/people/brandon-f` (a signature is about the signer, so it keeps the full name) |
| New: `/people/brandon-f` | none | Full name as the heading, bio, the TreadLightlyAI disclosure, and the published claims this person reviewed (newest first, `ClaimRow`) |

Out of scope: post and action bylines ("Written by Brandon Faloona", `src/content.config.ts:447,465`) are authorship, not review; README's operator line is a disclosure about the operator. Both keep the full name.

## Global Constraints

- Copy rules (`docs/decisions.md`): plain words, no em dashes; "TreadLightlyAI" is one word.
- The handle is written exactly as `brandon-f` (lowercase) wherever it is display text.
- The TreadLightlyAI disclosure keeps the current About wording ("He also makes TreadLightlyAI, an AI chatbot. When TreadLightlyAI shows up here, ...") on both the profile and About; it is about this one person, so "he" stays.
- A raw reviewer value (email) never reaches rendered HTML (`src/lib/reviewers.ts` comment).
- An unmapped reviewer value fails the build (existing behavior, kept).
- Links to the profile come from `profileHref()`; no page hard-codes `/people/brandon-f`.
- Pages follow existing layout patterns: `Base` with `layout="reading"` and `Breadcrumb`, like `src/pages/about.astro`.

## Review Focus

- A claim whose audit sidecar has an empty or missing reviewer: shows "Unreviewed", no profile link, and is not on any profile list.
- A draft or archived claim reviewed by the person: not listed on the profile (only `status === 'published'`).
- A reviewer email in different case or with spaces: still resolves (existing `trim().toLowerCase()`).
- A person in `reviewers.ts` with no page file: the build check fails, rather than claim pages linking to a 404.
- Dark mode and narrow screens on the profile claim list: reuses `ClaimRow` and `.claims-list`, so no new styles; check at 375px.

---

### Task 1: People data, claim page, and the build check

**Files:**
- Create: `scripts/check-reviewer-display.ts`
- Modify: `package.json` (add `check:reviewers`; it joins `check` in Task 3)
- Modify: `src/lib/reviewers.ts`
- Modify: `src/pages/research/claims/[...slug].astro:244`

**Interfaces:**
- Produces:
  - `interface Person { handle: string; fullName: string }`
  - `PEOPLE: Person[]`
  - `OPERATOR_HANDLE: string` (the person who runs the site; About and the research index use it, so list order never matters)
  - `operator(): Person` (the `PEOPLE` entry for `OPERATOR_HANDLE`; throws if absent)
  - `profileHref(person: Person): string` returns `/people/${handle}`
  - `resolveReviewer(raw, context): ReviewerDisplay | null`, where `ReviewerDisplay` is `{ person: Person; name: string /* the handle */; href: string }`
  - `reviewerHandle(raw): string | null` (for the profile claim list; never throws, returns null for empty or unmapped)
  - `npm run check:reviewers`

- [x] **Step 1: Write the check**

`scripts/check-reviewer-display.ts`:

```ts
// Checks built HTML, so run after `astro build`. Reviewer mentions show the
// handle and link the profile; the full name lives on the profile page (and the
// Values signature, which is not checked here).
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { PEOPLE, reviewerHandle } from '../src/lib/reviewers';

const DIST = 'dist';
const errors: string[] = [];

// Email matching tolerates case and spaces; empty or unknown values map to no one.
if (reviewerHandle(' Brandon@DangerousRobot.org ') !== 'brandon-f') errors.push('reviewerHandle: case/space variant did not resolve');
if (reviewerHandle('') !== null || reviewerHandle('x@y.z') !== null) errors.push('reviewerHandle: empty or unknown value resolved');

function htmlFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? htmlFiles(p) : name.endsWith('.html') ? [p] : [];
  });
}

const claimPages = htmlFiles(join(DIST, 'research/claims'));
if (claimPages.length === 0) errors.push('no claim pages in dist/; run `npm run build` first');

const handleOnly = [
  ...claimPages,
  join(DIST, 'research/index.html'),
  join(DIST, 'corrections/index.html'),
  join(DIST, 'about/index.html'),
];

for (const person of PEOPLE) {
  const profile = join(DIST, 'people', person.handle, 'index.html');
  if (!existsSync(profile)) {
    errors.push(`missing profile page for ${person.handle}: ${profile}`);
  } else if (!readFileSync(profile, 'utf8').includes(person.fullName)) {
    errors.push(`${profile}: does not show the full name`);
  }
  for (const file of handleOnly) {
    if (!existsSync(file)) continue;
    const html = readFileSync(file, 'utf8');
    if (html.includes(person.fullName)) errors.push(`${file}: prints full name "${person.fullName}"`);
  }
  let reviewed = 0;
  for (const file of claimPages) {
    const html = readFileSync(file, 'utf8');
    if (html.includes('review-state unreviewed')) {
      if (html.includes('href="/people/')) errors.push(`${file}: unreviewed claim links a profile`);
      continue;
    }
    if (!html.includes('review-state reviewed')) continue;
    reviewed++;
    if (!html.includes(`href="/people/${person.handle}"`)) errors.push(`${file}: reviewer line does not link /people/${person.handle}`);
    if (!html.includes(`>${person.handle}</a>`)) errors.push(`${file}: reviewer line does not show the handle ${person.handle}`);
  }
  if (reviewed === 0) errors.push('no reviewed claim pages found; the check would pass vacuously');
  // Drafts and unreviewed claims stay off the profile: its claim links must
  // match the reviewed claim pages one for one.
  if (existsSync(profile)) {
    const listed = new Set(readFileSync(profile, 'utf8').match(/href="\/research\/claims\/[^"]+"/g) ?? []).size;
    if (listed !== reviewed) errors.push(`${profile}: lists ${listed} claims, but ${reviewed} claim pages are reviewed`);
  }
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}
console.log(`check-reviewer-display: ${claimPages.length} claim pages, ${PEOPLE.length} profiles ok`);
```

The `reviewed === 0` guard is the known-positive control: three committed claims carry a reviewer today (`research/**/*.audit.yaml`), so a run that finds none means the check is broken, not clean. The unreviewed branch has no committed example yet (the two `reviewer: null` sidecars are uncommitted `us-data-centers` drafts); note in the task report whether any built claim page hit that branch. The per-person link check and the profile count assume one person; with a second person, each claim must be matched to its own reviewer.

In `package.json` add `"check:reviewers": "tsx scripts/check-reviewer-display.ts"`. Do not add it to `check` yet.

- [x] **Step 2: Run it, expect FAIL.** `npm run build`, then `npm run check:reviewers`. Expected: fails to import `reviewerHandle` and `PEOPLE` (not exported yet).

- [x] **Step 3: Rewrite `reviewers.ts`**

```ts
export interface Person {
  handle: string;
  fullName: string;
}

export interface ReviewerDisplay {
  person: Person;
  name: string;
  href: string;
}

export const PEOPLE: Person[] = [
  { handle: 'brandon-f', fullName: 'Brandon Faloona' },
];

export const OPERATOR_HANDLE = 'brandon-f';

// Audit sidecars store the reviewer as an email address. Readers see the
// handle linked to the profile instead, so an address never reaches the
// rendered page. Keys are lowercase; values are handles in PEOPLE.
const REVIEWER_HANDLES: Record<string, string> = {
  'brandon@dangerousrobot.org': 'brandon-f',
};

export function profileHref(person: Person): string {
  return `/people/${person.handle}`;
}

export function operator(): Person {
  const person = PEOPLE.find((p) => p.handle === OPERATOR_HANDLE);
  if (!person) throw new Error(`OPERATOR_HANDLE ${OPERATOR_HANDLE} has no entry in PEOPLE`);
  return person;
}

export function reviewerHandle(raw: string | null | undefined): string | null {
  if (!raw) return null;
  return REVIEWER_HANDLES[raw.trim().toLowerCase()] ?? null;
}

/**
 * Display info for a raw reviewer value, or null when the value is empty.
 * Throws on a value with no mapping, failing the build: a reviewed claim must
 * name the person who stands behind it. Callers must never print the raw value.
 */
export function resolveReviewer(raw: string | null | undefined, context: string): ReviewerDisplay | null {
  if (!raw) return null;
  const person = PEOPLE.find((p) => p.handle === reviewerHandle(raw));
  if (!person) {
    throw new Error(`${context}: reviewer has no entry in src/lib/reviewers.ts; add one before building`);
  }
  return { person, name: person.handle, href: profileHref(person) };
}
```

- [x] **Step 4: Claim page.** The header line (`:127-129`) already renders `reviewer.name` and `reviewer.href`; no markup change. Change the audit line (`:244`) to link the handle:

```astro
<p>Reviewed {reviewedAt}{reviewer && <> by <a href={reviewer.href}>{reviewer.name}</a></>}</p>
```

- [x] **Step 5: Run.** `npm run check:types`, then `npm run build && npm run check:reviewers`. Expected: types pass; the check fails only on `missing profile page for brandon-f` and on full-name hits in research index, corrections and about. No claim page errors.
- [x] **Step 6: Commit** `scripts/check-reviewer-display.ts`, `package.json`, `src/lib/reviewers.ts`, `src/pages/research/claims/[...slug].astro`: `feat(site): show the reviewer's handle on claim pages`.

### Task 2: Profile page

**Files:**
- Create: `src/pages/people/brandon-f.astro`

**Interfaces:**
- Consumes: `PEOPLE`, `reviewerHandle` (Task 1); `ClaimRow` (`src/components/ClaimRow.astro`).

- [x] **Step 1: Write the page**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../../layouts/Base.astro';
import Breadcrumb from '../../components/Breadcrumb.astro';
import ClaimRow from '../../components/ClaimRow.astro';
import { PEOPLE, reviewerHandle } from '../../lib/reviewers';

const person = PEOPLE.find((p) => p.handle === 'brandon-f')!;
const isoDay = (d: unknown) => (d instanceof Date ? d.toISOString().split('T')[0] : String(d));
const reviewed = (await getCollection('claims', ({ data }) =>
  data.status === 'published' && reviewerHandle(data.audit?.human_review.reviewer) === person.handle,
)).sort((a, b) => isoDay(b.data.as_of).localeCompare(isoDay(a.data.as_of)));
---
<Base title={person.fullName} description={`${person.fullName} runs Dangerous Robot and reviews every claim on it.`} layout="reading">
  <article class="reading">
    <Breadcrumb crumbs={[
      { label: 'Home', href: '/' },
      { label: 'About', href: '/about' },
      { label: person.fullName },
    ]} />
    <h1>{person.fullName}</h1>
    <p>
      Brandon Faloona ({person.handle} on this site) runs Dangerous Robot and reviews every claim on it. He also makes TreadLightlyAI, an AI chatbot. When TreadLightlyAI shows up here, it is held to the same criteria and sources as every other product, and the site does not publish verdicts on claims about it.
    </p>
    <h2>Claims reviewed</h2>
    {reviewed.length === 0 ? <p>None published yet.</p> : (
      <div class="claims-list">
        {reviewed.map((claim) => (
          <ClaimRow
            id={claim.id}
            title={claim.data.title}
            verdict={claim.data.verdict}
            entity={claim.data.entity}
            topics={claim.data.topics}
            asOf={isoDay(claim.data.as_of)}
            confidence={claim.data.confidence}
          />
        ))}
      </div>
    )}
  </article>
</Base>
```

The bio is the current About "Who runs this" text, moved, with the handle added so a reader who followed a `brandon-f` link knows they are on the right page. It is about this one person, so it keeps the full name and "he".

- [x] **Step 2: Check `.claims-list` styling.** It is defined for the claims index; if it is scoped to that page, move the rule to a shared stylesheet rather than copying it. Screenshot `/people/brandon-f` at 375px and 1280px, light and dark (`inv dev`, port 4321; don't start a second server if one is running).
- [x] **Step 3: Run.** `npm run build && npm run check:reviewers`. Expected: fails only on full-name hits in research index, corrections and about.
- [x] **Step 4: Commit** `feat(site): add the reviewer profile page`.

### Task 3: Other reviewer mentions

**Files:**
- Modify: `src/pages/research/index.astro:26, 82, 161, 369`
- Modify: `src/pages/corrections.astro:28`
- Modify: `src/pages/about.astro:44-49`
- Modify: `src/pages/values.astro:68`
- Modify: `package.json` (`check` script)

- [x] **Step 1: Edit copy** per the § Design table. Import `operator` and `profileHref` from `src/lib/reviewers.ts` where a link or name is rendered; the JSON-LD strings use the plain handle via `operator().handle`. About "Who runs this" becomes:

```astro
<p>
  <a href={profileHref(op)}>{op.handle}</a> runs Dangerous Robot and reviews every claim on it. He also makes TreadLightlyAI, an AI chatbot. When TreadLightlyAI shows up here, it is held to the same criteria and sources as every other product, and the site does not publish verdicts on claims about it.
</p>
```

where `const op = operator();`. Keep the `id="who-runs-this"` anchor so existing links still land. The Values signature keeps "Brandon Faloona" as text (`{op.fullName}`) and links `profileHref(op)`.

- [x] **Step 2: Wire the check in.** Append `&& npm run check:reviewers` to `check` in `package.json`, after `npm run build`.
- [x] **Step 3: Run.** `npm run check` (types, build, markdown lint, citations, reviewers). Expected: PASS. Also confirm a negative: temporarily change one claim page's `reviewer.name` to `person.fullName`, rebuild, and see the check fail; revert.
- [x] **Step 4: Commit** `feat(site): show the reviewer's handle across the site`.

### Task 4: Docs

**Files:**
- Modify: `docs/decisions.md` (new 2026-10-07 or later entry; copy table row "Reviewer line (claim pages)" at `:33`)
- Modify: `docs/mission-and-voice.md:34, 157`
- Modify: `docs/architecture/site.md:221` (also fix its stale "an unmapped value prints no name"; the build fails instead)
- Modify: `docs/v1.0.0-roadmap.md` (SITE-N status, commit refs)

- [x] **Step 1:** Add a dated entry: "**Reviewer named by handle.** Pages that name the claim reviewer show the reviewer's handle (`brandon-f`), linked to `/people/<handle>`, which carries the full name, bio and reviewed claims. The Values signature keeps the full name. *(Final)*". Update the copy table row to "Reviewed and approved by brandon-f (the handle links to `/people/brandon-f`)".
- [x] **Step 2:** Update the other three docs to match; describe `PEOPLE`, `REVIEWER_HANDLES`, `operator()` and the build check in `site.md`.
- [x] **Step 3:** Tick this plan, mark SITE-N `done` with commit refs.
- [x] **Step 4: Commit** `docs: record the handle reviewer line and profile page`.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-07 | agent (claude-opus-5-5, advisor pass) | implementation, iterated | Checked file paths and line refs against the code; added tests for email matching, unreviewed claims and the profile claim count; resolved the disclosure wording conflict; `OPERATOR_HANDLE` instead of list order |
| 2026-10-07 | human (operator) | basic, iterated | Handle `brandon-f`; reviewer display text is the handle; Values signature keeps the full name and links the profile |
| 2026-10-07 | agent (claude-opus-5-5) | implementation | Shipped; follow-ups recorded on the roadmap item: review copy says a person reviews, the full-name scan was dropped (`e70d9d9`), and the profile shows a photo when one exists (`a04756c`) |

// Checks built HTML, so run after `astro build`. Reviewer mentions show the
// handle and link the profile; the full name lives on the profile page (and the
// Values signature, which is not checked here).
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { PEOPLE, reviewerHandle } from '../src/lib/reviewers';

// Override only to run the check against a scratch copy of the build.
const DIST = process.env.REVIEWER_CHECK_DIST ?? 'dist';
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

const stripSlash = (path: string) => path.replace(/\/+$/, '');

// dist/research/claims/<id>/index.html -> /research/claims/<id>
function claimPath(file: string): string {
  return stripSlash('/' + relative(DIST, file).split(sep).join('/').replace(/(^|\/)index\.html$/, ''));
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
  // Claim paths of reviewed, published claim pages, as ClaimRow links them.
  const reviewed = new Set<string>();
  for (const file of claimPages) {
    const html = readFileSync(file, 'utf8');
    if (html.includes('review-state unreviewed')) {
      if (html.includes('href="/people/')) errors.push(`${file}: unreviewed claim links a profile`);
      continue;
    }
    if (!html.includes('review-state reviewed')) continue;
    if (!html.includes(`href="/people/${person.handle}"`)) errors.push(`${file}: reviewer line does not link /people/${person.handle}`);
    if (!html.includes(`>${person.handle}</a>`)) errors.push(`${file}: reviewer line does not show the handle ${person.handle}`);
    const status = html.match(/data-claim-status="([^"]*)"/)?.[1];
    if (status === undefined) errors.push(`${file}: reviewed claim page has no data-claim-status`);
    // Archived and draft pages still build, but the profile lists published claims only.
    if (status !== 'published') continue;
    reviewed.add(claimPath(file));
  }
  if (reviewed.size === 0) errors.push('no reviewed published claim pages found; the check would pass vacuously');
  // Drafts, archived and unreviewed claims stay off the profile: its claim
  // links must match the reviewed published claim pages exactly.
  if (existsSync(profile)) {
    const listed = new Set(
      [...readFileSync(profile, 'utf8').matchAll(/href="(\/research\/claims\/[^"#?]+)"/g)].map((m) => stripSlash(m[1])),
    );
    for (const path of reviewed) if (!listed.has(path)) errors.push(`${profile}: missing reviewed claim ${path}`);
    for (const path of listed) if (!reviewed.has(path)) errors.push(`${profile}: lists ${path}, which is not a reviewed published claim page`);
  }
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}
console.log(`check-reviewer-display: ${claimPages.length} claim pages, ${PEOPLE.length} profiles ok`);

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

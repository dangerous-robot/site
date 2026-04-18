/**
 * Citation integrity check.
 *
 * Verifies that every source slug in a claim's `sources` frontmatter array
 * has a corresponding file at research/sources/<slug>.md.
 *
 * Exits 0 if all citations resolve (or no claims exist).
 * Exits 1 if any broken references are found.
 */

import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import matter from "gray-matter";

const CLAIMS_DIR = "research/claims";
const SOURCES_DIR = "research/sources";

function collectMarkdownFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectMarkdownFiles(full));
    } else if (entry.name.endsWith(".md")) {
      files.push(full);
    }
  }
  return files;
}

const claimFiles = collectMarkdownFiles(CLAIMS_DIR);

if (claimFiles.length === 0) {
  console.log("No claim files found -- skipping citation check.");
  process.exit(0);
}

let broken = 0;

for (const file of claimFiles) {
  const raw = readFileSync(file, "utf-8");
  const { data } = matter(raw);
  const sources: unknown = data.sources;

  if (!Array.isArray(sources)) continue;

  for (const slug of sources) {
    if (typeof slug !== "string") continue;
    const sourcePath = join(SOURCES_DIR, `${slug}.md`);
    if (!existsSync(sourcePath) || !statSync(sourcePath).isFile()) {
      console.error(`BROKEN: ${relative(".", file)} references "${slug}" but ${sourcePath} does not exist`);
      broken++;
    }
  }
}

if (broken > 0) {
  console.error(`\n${broken} broken citation(s) found.`);
  process.exit(1);
} else {
  console.log(`All citations valid across ${claimFiles.length} claim file(s).`);
}

#!/usr/bin/env node
// Regenerates the three interactive analysis artifacts from the committed data
// files. Self-contained HTML (inline CSS+JS+data): safe for strict-CSP hosting.
//
//   node docs/reports/codebase-analysis-2026-07/generate-artifacts.mjs
//
// Requires devDeps: esbuild, d3-selection, d3-zoom, d3-scale, d3-cloud.
import { build } from "esbuild";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DATA = (name) => JSON.parse(readFileSync(join(HERE, "data", name), "utf8"));
const css = readFileSync(join(HERE, "artifacts/src/shared.css"), "utf8");

const architecture = DATA("architecture.json");
const findingsFile = DATA("findings.json");
const terminology = DATA("terminology.json");
const metrics = DATA("metrics.json");
const wordFreq = Object.fromEntries(
  ["docs", "pipeline-identifiers", "site-identifiers", "ui-copy"].map((k) => [
    k, JSON.parse(readFileSync(join(HERE, "data/word-frequency", `${k}.json`), "utf8")),
  ]),
);

const findingsById = Object.fromEntries(
  findingsFile.findings.map((f) => [f.id, { title: f.title, severity: f.severity, status: f.status, category: f.category }]),
);
const metricsMeta = {
  commit: metrics.provenance.commit,
  tools: `lizard ${metrics.provenance.tools.lizard}, networkx ${metrics.provenance.tools.networkx}`,
};

const PAGES = [
  {
    entry: "explorer.js", out: "architecture-explorer.html",
    title: "Architecture explorer — dangerousrobot.org codebase analysis",
    data: { arch: architecture, findingsById },
  },
  {
    entry: "taxonomy.js", out: "taxonomy-explorer.html",
    title: "Taxonomy & glossary — dangerousrobot.org codebase analysis",
    data: { terminology, wordFreq },
  },
  {
    entry: "findings.js", out: "findings-dashboard.html",
    title: "Findings dashboard — dangerousrobot.org codebase analysis",
    data: {
      findings: findingsFile.findings,
      cleanSlates: findingsFile.clean_slates,
      hotspots: metrics.hotspots_top30,
      metricsMeta,
    },
  },
];

for (const page of PAGES) {
  const bundle = await build({
    entryPoints: [join(HERE, "artifacts/src", page.entry)],
    bundle: true, write: false, format: "iife", minify: true,
    target: "es2020",
  });
  const js = bundle.outputFiles[0].text;
  // </script injection guard for inlined JSON
  const dataJson = JSON.stringify(page.data).replace(/</g, "\\u003c");
  const html = `<meta charset="utf-8" />
<title>${page.title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>${css}</style>
<body>
<script>window.DATA = ${dataJson};</script>
<script defer>${js}</script>`;
  writeFileSync(join(HERE, "artifacts", page.out), html);
  console.log(`${page.out}: ${(html.length / 1024).toFixed(0)} KB`);
}

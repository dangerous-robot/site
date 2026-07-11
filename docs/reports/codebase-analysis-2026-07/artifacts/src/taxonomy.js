// Taxonomy + glossary explorer. Primary view: the concept/collision table
// (where the same idea wears 2+ names, or one word means 2+ things), with a
// per-concept drawer showing verbatim sample occurrences and the recommended
// canonical term. Word clouds are the secondary panel, one per corpus.
import cloud from "d3-cloud";
import { el, svgEl, initTheme, tooltip, esc } from "./shared.js";

const { terminology, wordFreq } = window.DATA;
const tip = tooltip();

const topbar = el("div", { class: "topbar" });
topbar.append(el("div", { class: "brand" },
  el("div", { class: "eyebrow" }, "dangerousrobot.org · codebase analysis · 2026-07"),
  el("div", { class: "title" }, "Taxonomy & glossary explorer")));
const tabs = ["concepts", "glossary", "word clouds"].map((t, i) =>
  el("button", { class: "btn", "aria-pressed": String(i === 0) }, t));
topbar.append(el("div", { class: "controls" }, ...tabs), el("div", { class: "spacer" }));
initTheme(topbar);
document.body.append(topbar);

const wrap = el("div", { class: "wrap" });
document.body.append(wrap);
const views = { concepts: el("div"), glossary: el("div"), "word clouds": el("div") };
wrap.append(views.concepts, views.glossary, views["word clouds"]);

tabs.forEach((b, i) => b.addEventListener("click", () => {
  tabs.forEach((x, j) => x.setAttribute("aria-pressed", String(i === j)));
  Object.values(views).forEach((v, j) => (v.style.display = i === j ? "" : "none"));
  if (i === 2) buildClouds();
}));
views.glossary.style.display = "none";
views["word clouds"].style.display = "none";

// ---------------- concepts ----------------
const LAYERS = ["docs", "pipeline", "src", "ui"];
const concepts = [...terminology.concepts].sort((a, b) => (b.variants?.length || 0) - (a.variants?.length || 0));

const kpis = el("div", { class: "tiles", style: "margin-bottom:14px" });
const nCollisions = concepts.filter((c) => c.collision).length;
const nVariants = concepts.reduce((s, c) => s + (c.variants?.length || 0), 0);
kpis.innerHTML = `
  <div class="tile"><div class="k">concepts tracked</div><div class="v">${concepts.length}</div><div class="d">ideas with contested naming</div></div>
  <div class="tile"><div class="k">name variants</div><div class="v">${nVariants}</div><div class="d">across docs · pipeline · src · ui</div></div>
  <div class="tile"><div class="k">collisions</div><div class="v">${nCollisions}</div><div class="d">same word, 2+ meanings</div></div>
  <div class="tile"><div class="k">glossary entries</div><div class="v">${terminology.glossary.length}</div><div class="d">proposed definitions</div></div>`;
views.concepts.append(kpis);

const grid = el("div", { style: "display:grid;grid-template-columns:1fr 400px;gap:14px;align-items:start" });
views.concepts.append(grid);
const tablePanel = el("div", { class: "panel" });
const drawer = el("div", { class: "panel", style: "position:sticky;top:76px;max-height:calc(100vh - 96px);overflow:auto" });
drawer.innerHTML = `<div class="panel-body note">Select a concept to see every name it wears, verbatim sample occurrences, and the recommended canonical term with its migration blast radius.</div>`;
grid.append(tablePanel, drawer);

const rows = concepts.map((c, i) => {
  const layers = new Set((c.variants || []).map((v) => v.layer));
  return `<tr data-i="${i}" tabindex="0" style="cursor:pointer">
    <td><b>${esc(c.concept)}</b>${c.collision ? ' <span class="chip sev-medium"><span class="dot"></span>collision</span>' : ""}</td>
    <td>${(c.variants || []).slice(0, 6).map((v) => `<code>${esc(v.term)}</code>`).join(" · ")}${(c.variants || []).length > 6 ? " …" : ""}</td>
    <td>${LAYERS.map((l) => layers.has(l) ? `<span class="layer-chip layer-${l}">${l}</span>` : "").join(" ")}</td>
    <td><code>${esc(c.recommendation?.canonical || "—")}</code></td>
  </tr>`;
}).join("");
tablePanel.innerHTML = `
  <div class="panel-head"><h2>Concepts with contested names</h2>
    <span class="note">sorted by variant count · click for evidence</span></div>
  <div class="panel-body" style="padding:0;overflow-x:auto">
  <table class="data"><thead><tr><th>concept</th><th>variant names</th><th>layers</th><th>recommended</th></tr></thead>
  <tbody>${rows}</tbody></table></div>`;

function showConcept(i) {
  const c = concepts[i];
  drawer.innerHTML = `
    <div class="panel-head"><h2>${esc(c.concept)}</h2></div>
    <div class="panel-body">
      ${c.collision ? `<p style="margin-top:0"><b>Collision:</b> ${esc(c.collision)}</p>` : ""}
      <h3 style="font-size:12px;margin:8px 0 6px">Variants & where they live</h3>
      ${(c.variants || []).map((v) => `
        <div style="margin-bottom:10px">
          <code>${esc(v.term)}</code> <span class="layer-chip layer-${esc(v.layer)}">${esc(v.layer)}</span>
          <span class="fileref"> ${esc(v.count_source || "")}</span>
          ${v.sample ? `<div class="quote">${esc(v.sample.quote)}<br/><span class="fileref">${esc(v.sample.file)}:${esc(v.sample.line)}</span></div>` : ""}
        </div>`).join("")}
      ${c.recommendation ? `
        <h3 style="font-size:12px;margin:14px 0 6px">Recommendation</h3>
        <p style="margin:0 0 4px">Canonical: <code><b>${esc(c.recommendation.canonical)}</b></code></p>
        <p style="margin:0 0 4px">${esc(c.recommendation.rationale || "")}</p>
        <p class="note"><b>Blast radius:</b> ${esc(c.recommendation.blast_radius || "—")}</p>` : ""}
      ${(c.alt_recommendations || []).length ? `<p class="note"><b>Dissent:</b> ${c.alt_recommendations.map((r) => `${esc(r.from)} prefers <code>${esc(r.canonical)}</code>`).join("; ")}</p>` : ""}
    </div>`;
}
tablePanel.querySelectorAll("tr[data-i]").forEach((tr) => {
  const go = () => showConcept(+tr.dataset.i);
  tr.addEventListener("click", go);
  tr.addEventListener("keydown", (e) => e.key === "Enter" && go());
});

// ---------------- glossary ----------------
const gl = [...terminology.glossary].sort((a, b) => a.term.localeCompare(b.term));
views.glossary.append(el("div", { class: "panel" }));
views.glossary.firstChild.innerHTML = `
  <div class="panel-head"><h2>Proposed glossary</h2>
    <span class="note">terms a confused reader or contributor needs; "confusables" are the words people reach for instead</span></div>
  <div class="panel-body" style="padding:0;overflow-x:auto">
  <table class="data"><thead><tr><th>term</th><th>plain definition</th><th>confusables</th><th>audience</th></tr></thead>
  <tbody>${gl.map((g) => `<tr>
    <td><code><b>${esc(g.term)}</b></code></td>
    <td style="max-width:460px">${esc(g.plain_definition)}</td>
    <td>${(g.confusables || []).map((x) => `<code>${esc(x)}</code>`).join(", ")}</td>
    <td><span class="chip"><span class="dot" style="background:var(--s5)"></span>${esc(g.audience || "both")}</span></td>
  </tr>`).join("")}</tbody></table></div>`;

// ---------------- word clouds (secondary, canvas-measured layout) ----------------
const CORPORA = [
  { key: "docs", title: "Docs prose", field: "words", note: "what contributors write about" },
  { key: "pipeline-identifiers", title: "Pipeline identifiers", field: "word_parts", note: "what the Python code calls things" },
  { key: "site-identifiers", title: "Site identifiers", field: "word_parts", note: "what the TypeScript/Astro code calls things" },
  { key: "ui-copy", title: "Reader-visible copy", field: "words", note: "what readers actually see" },
];
let cloudsBuilt = false;
function buildClouds() {
  if (cloudsBuilt) return;
  cloudsBuilt = true;
  views["word clouds"].append(el("p", { class: "note" },
    "Font size encodes frequency (data: data/word-frequency/*.json). One hue per corpus — color marks corpus identity, not magnitude. Hover a word for its exact count."));
  const grid2 = el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px" });
  views["word clouds"].append(grid2);
  const hues = ["var(--s1)", "var(--s2)", "var(--s5)", "var(--s8)"];
  CORPORA.forEach((c, ci) => {
    const data = (wordFreq[c.key]?.[c.field] || []).slice(0, 80);
    const max = data[0]?.[1] || 1;
    const panel = el("div", { class: "panel" });
    panel.innerHTML = `<div class="panel-head"><h2>${esc(c.title)}</h2><span class="note">${esc(c.note)}</span></div>`;
    const body = el("div", { class: "panel-body", style: "padding:4px" });
    panel.append(body);
    grid2.append(panel);
    const W = 460, H = 320;
    cloud()
      .size([W, H])
      .words(data.map(([text, count]) => ({ text, count, size: 11 + 34 * Math.sqrt(count / max) })))
      .padding(2)
      .rotate(0)
      .font("ui-monospace, Menlo, monospace")
      .fontSize((d) => d.size)
      .on("end", (words) => {
        const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, style: "width:100%;display:block" });
        const g = svgEl("g", { transform: `translate(${W / 2},${H / 2})` });
        svg.append(g);
        for (const w of words) {
          const t = svgEl("text", {
            x: w.x, y: w.y, "font-size": w.size, fill: hues[ci],
            "text-anchor": "middle", class: "monolabel", opacity: 0.55 + 0.45 * (w.count / max),
          });
          t.textContent = w.text;
          t.addEventListener("mousemove", (ev) => tip.show(
            `<div class="tip-title mono">${esc(w.text)}</div><div class="tip-sub">${w.count} occurrences · ${esc(c.title)}</div>`,
            ev.clientX, ev.clientY));
          t.addEventListener("mouseleave", () => tip.hide());
          g.append(t);
        }
        body.append(svg);
      })
      .start();
  });
}

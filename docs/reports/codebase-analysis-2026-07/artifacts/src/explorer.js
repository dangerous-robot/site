// Architecture explorer: zoomable L1→L2→L3 drill-down over architecture.json.
// Not a force-directed hairball (graphify's graph.html already is one): this is
// a containment map — actors/externals in a context band, the system's five
// containers as boxes, components as tiles inside them. Edges draw on demand.
import { select } from "d3-selection";
import { zoom, zoomIdentity } from "d3-zoom";
import { el, svgEl, initTheme, tooltip, esc, sevChip, statusChip } from "./shared.js";

const { arch, findingsById } = window.DATA;
const tip = tooltip();

const nodes = arch.nodes;
const byId = new Map(nodes.map((n) => [n.id, n]));
const l2 = nodes.filter((n) => n.level === "l2");
const l3 = nodes.filter((n) => n.level === "l3");
const ctx = nodes.filter((n) => n.level === "l1" && n.kind !== "system");
const kidsOf = (pid) => l3.filter((n) => n.parent === pid);

// ---------- layout ----------
const TILE_W = 172, TILE_H = 64, TILE_GAP = 10, PAD = 16, HEAD = 44;
const COLS_FOR = (n) => (n <= 4 ? 2 : n <= 9 ? 3 : 4);
const CANVAS_W = 1560;

const containers = [];
{
  // context band (actors + externals) across the top
  const bandY = 0, bandH = 92;
  ctx.forEach((n, i) => {
    n._x = 10 + i * ((CANVAS_W - 20) / ctx.length);
    n._y = bandY + 10;
    n._w = (CANVAS_W - 20) / ctx.length - 14;
    n._h = bandH - 20;
  });
  // L2 containers: two rows, sized by child count
  let x = 0, y = bandH + 34, rowH = 0, rowIdx = 0;
  for (const c of l2) {
    const kids = kidsOf(c.id);
    const cols = COLS_FOR(kids.length);
    const rows = Math.max(1, Math.ceil(kids.length / cols));
    c._w = PAD * 2 + cols * TILE_W + (cols - 1) * TILE_GAP;
    c._h = HEAD + PAD + rows * TILE_H + (rows - 1) * TILE_GAP + PAD;
    if (x + c._w > CANVAS_W && rowIdx > 0) { x = 0; y += rowH + 26; rowH = 0; rowIdx = 0; }
    c._x = x; c._y = y;
    x += c._w + 26; rowH = Math.max(rowH, c._h); rowIdx++;
    kids.sort((a, b) => (b.metrics?.loc || 0) - (a.metrics?.loc || 0));
    kids.forEach((k, i) => {
      const col = i % cols, row = Math.floor(i / cols);
      k._x = c._x + PAD + col * (TILE_W + TILE_GAP);
      k._y = c._y + HEAD + PAD / 2 + row * (TILE_H + TILE_GAP);
      k._w = TILE_W; k._h = TILE_H;
    });
    containers.push(c);
  }
}
const CANVAS_H = Math.max(...l2.map((c) => c._y + c._h)) + 40;

// ---------- chrome ----------
const topbar = el("div", { class: "topbar" });
topbar.append(el("div", { class: "brand" },
  el("div", { class: "eyebrow" }, "dangerousrobot.org · codebase analysis · 2026-07"),
  el("div", { class: "title" }, "Architecture explorer")));
const search = el("input", { type: "search", placeholder: "find component…", "aria-label": "Find component" });
const modeBtn = el("button", { class: "btn", "aria-pressed": "false" }, "proposed changes: off");
const resetBtn = el("button", { class: "btn" }, "reset view");
const legend = el("div", { class: "legend" });
legend.innerHTML = `
  <span class="li"><span class="sw" style="background:var(--accent)"></span>selected edge</span>
  <span class="li"><span class="sw" style="border:1.5px solid var(--baseline);background:transparent"></span>import (deterministic)</span>
  <span class="li"><span class="sw" style="border:1.5px dashed var(--baseline);background:transparent"></span>dataflow (analyst)</span>
  <span class="li"><span class="chip sev-high"><span class="dot"></span>high</span></span>
  <span class="li"><span class="chip sev-medium"><span class="dot"></span>med</span></span>
  <span class="li">Δ = proposed change</span>`;
topbar.append(el("div", { class: "controls" }, search, modeBtn, resetBtn), el("div", { class: "spacer" }), legend);
initTheme(topbar);
document.body.append(topbar);

const wrap = el("div", { class: "wrap", style: "display:grid;grid-template-columns:1fr 360px;gap:14px;align-items:start;" });
const svgPanel = el("div", { class: "panel svgwrap" });
const detail = el("div", { class: "panel", style: "position:sticky;top:76px;max-height:calc(100vh - 96px);overflow:auto;" });
detail.innerHTML = `<div class="panel-body note">Click a container or component. Scroll to zoom, drag to pan.
<br/><br/>Tiles show lines of code (bar), hotspot rank (#), and finding severity dots.
Edge provenance is styled: solid = deterministic import graph; dashed = analyst-judged dataflow.</div>`;
wrap.append(svgPanel, detail);
document.body.append(wrap);

// ---------- svg scene ----------
const svg = svgEl("svg", { viewBox: `0 0 ${CANVAS_W} ${CANVAS_H}`, style: "width:100%;height:calc(100vh - 120px);display:block;background:var(--page);" });
svg.setAttribute("role", "img");
svg.setAttribute("aria-label", "Zoomable architecture map");
const scene = svgEl("g", {});
const edgeLayer = svgEl("g", {});
const nodeLayer = svgEl("g", {});
scene.append(edgeLayer, nodeLayer);
svg.append(scene);
svgPanel.append(svg);

let proposedMode = false;
let selected = null;

function sevDots(n) {
  const fids = (n.finding_ids || []).map((id) => findingsById[id]).filter(Boolean)
    .filter((f) => f.status === "confirmed");
  const c = { high: 0, medium: 0, low: 0 };
  fids.forEach((f) => c[f.severity] !== undefined && c[f.severity]++);
  return c;
}

function drawNode(n) {
  const isL2 = n.level === "l2";
  const isCtx = n.level === "l1";
  const g = svgEl("g", { cursor: "pointer" });
  g.setAttribute("tabindex", "0");
  const hasProp = proposedMode && (n.proposed_changes || []).length;
  const rect = svgEl("rect", {
    x: n._x, y: n._y, width: n._w, height: n._h, rx: isL2 ? 12 : 8,
    fill: isCtx ? "transparent" : "var(--surface)",
    stroke: hasProp ? "var(--accent)" : "var(--border)",
    "stroke-width": hasProp ? 2 : 1,
    "stroke-dasharray": isCtx ? "4 3" : "none",
  });
  g.append(rect);
  const label = svgEl("text", {
    x: n._x + 10, y: n._y + (isL2 ? 20 : 16), fill: "var(--ink)",
    "font-size": isL2 ? 13 : 10.5, "font-weight": 650,
  });
  const name = n.name.length > (isL2 ? 60 : 26) ? n.name.slice(0, isL2 ? 58 : 24) + "…" : n.name;
  label.textContent = (hasProp ? "Δ " : "") + name;
  g.append(label);

  if (isL2 || isCtx) {
    const sub = svgEl("text", { x: n._x + 10, y: n._y + (isL2 ? 36 : 32), fill: "var(--muted)", "font-size": 9.5, class: "monolabel" });
    sub.textContent = isL2 ? (n.paths || []).join("  ") : (n.kind || "");
    g.append(sub);
  } else {
    // loc bar + hotspot + severity dots
    const loc = n.metrics?.loc || 0;
    const maxLoc = 4000;
    const bw = Math.max(3, Math.min(1, loc / maxLoc) * (n._w - 20));
    g.append(svgEl("rect", { x: n._x + 10, y: n._y + n._h - 14, width: n._w - 20, height: 4, rx: 2, fill: "var(--grid)" }));
    g.append(svgEl("rect", { x: n._x + 10, y: n._y + n._h - 14, width: bw, height: 4, rx: 2, fill: "var(--s1)" }));
    const rank = n.metrics?.best_hotspot_rank;
    if (rank && rank <= 30) {
      const t = svgEl("text", { x: n._x + n._w - 10, y: n._y + 16, fill: rank <= 5 ? "var(--critical)" : "var(--muted)", "font-size": 9.5, "text-anchor": "end", class: "monolabel" });
      t.textContent = "#" + rank;
      g.append(t);
    }
    const dots = sevDots(n);
    let dx = n._x + 10;
    for (const [sev, color] of [["high", "var(--critical)"], ["medium", "var(--serious)"], ["low", "var(--warning)"]]) {
      for (let i = 0; i < Math.min(dots[sev], 6); i++) {
        g.append(svgEl("circle", { cx: dx + 4, cy: n._y + 28, r: 3.2, fill: color }));
        dx += 10;
      }
    }
  }

  g.addEventListener("mousemove", (ev) => {
    const m = n.metrics || {};
    tip.show(`<div class="tip-title">${esc(n.name)}</div>
      <div class="tip-sub">${esc(n.role || "")}</div>
      ${n.level === "l3" ? `<div class="tip-sub mono">loc ${m.loc ?? "—"} · churn ${m.churn_commits ?? "—"} · ccn ${m.ccn_total ?? "—"}</div>` : ""}`,
      ev.clientX, ev.clientY);
  });
  g.addEventListener("mouseleave", () => tip.hide());
  g.addEventListener("click", (ev) => { ev.stopPropagation(); selectNode(n); });
  g.addEventListener("keydown", (ev) => { if (ev.key === "Enter") selectNode(n); });
  nodeLayer.append(g);
  n._g = g; n._rect = rect;
}

function center(n) { return [n._x + n._w / 2, n._y + n._h / 2]; }

function drawEdges() {
  edgeLayer.textContent = "";
  const showable = arch.edges.filter((e) => e.resolved !== false && byId.has(e.source) && byId.get(e.source)._x !== undefined && byId.has(e.target) && byId.get(e.target)._x !== undefined);
  const isSel = (e) => selected && (e.source === selected.id || e.target === selected.id);
  const l2ids = new Set(l2.map((n) => n.id).concat(ctx.map((n) => n.id)));
  for (const e of showable) {
    const bothTop = l2ids.has(e.source) && l2ids.has(e.target);
    if (!bothTop && !isSel(e)) continue;
    const a = byId.get(e.source), b = byId.get(e.target);
    const [x1, y1] = center(a), [x2, y2] = center(b);
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2 - Math.min(70, Math.abs(x2 - x1) / 5) - 8;
    const path = svgEl("path", {
      d: `M${x1},${y1} Q${mx},${my} ${x2},${y2}`,
      fill: "none",
      stroke: isSel(e) ? "var(--accent)" : "var(--baseline)",
      "stroke-width": isSel(e) ? 2 : 1.2,
      "stroke-dasharray": e.provenance === "deterministic" ? "none" : "5 4",
      opacity: isSel(e) ? 0.95 : 0.5,
      "marker-end": "url(#arr)",
    });
    path.addEventListener("mousemove", (ev) => tip.show(
      `<div class="tip-title mono">${esc(e.source)} → ${esc(e.target)}</div>
       <div class="tip-sub">${esc(e.type)}${e.label ? " · " + esc(e.label) : ""} · ${esc(e.provenance)}</div>`, ev.clientX, ev.clientY));
    path.addEventListener("mouseleave", () => tip.hide());
    edgeLayer.append(path);
  }
}

const defs = svgEl("defs", {});
defs.innerHTML = `<marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
  <path d="M0,0.5 L7.5,4 L0,7.5 z" fill="var(--baseline)"/></marker>`;
svg.append(defs);

ctx.forEach(drawNode);
l2.forEach(drawNode);
l3.forEach(drawNode);
drawEdges();

// ---------- zoom ----------
const zoomer = zoom().scaleExtent([0.5, 6]).on("zoom", (ev) => {
  scene.setAttribute("transform", ev.transform.toString());
});
select(svg).call(zoomer);
function zoomTo(n, scale = 2.2) {
  const [cx, cy] = center(n);
  const vw = CANVAS_W, vh = CANVAS_H;
  const s = n.level === "l2" ? Math.min(3, 0.85 * Math.min(vw / n._w, vh / n._h)) : scale;
  select(svg).transition().duration(matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 420)
    .call(zoomer.transform, zoomIdentity.translate(vw / 2 - s * cx, vh / 2 - s * cy).scale(s));
}
function clearDetail() {
  detail.innerHTML = `<div class="panel-body note">Click a container or component. Scroll to zoom, drag to pan.
<br/><br/>Tiles show lines of code (bar), hotspot rank (#), and finding severity dots.
Edge provenance is styled: solid = deterministic import graph; dashed = analyst-judged dataflow.</div>`;
}
resetBtn.addEventListener("click", () => {
  selected = null; restyle(); drawEdges(); clearDetail();
  select(svg).transition().duration(300).call(zoomer.transform, zoomIdentity);
});
svg.addEventListener("click", () => { selected = null; restyle(); drawEdges(); clearDetail(); });

// ---------- selection & detail panel ----------
function restyle() {
  for (const n of [...ctx, ...l2, ...l3]) {
    if (!n._rect) continue;
    const hasProp = proposedMode && (n.proposed_changes || []).length;
    n._rect.setAttribute("stroke", n === selected ? "var(--accent)" : hasProp ? "var(--accent)" : "var(--border)");
    n._rect.setAttribute("stroke-width", n === selected ? 2.5 : hasProp ? 2 : 1);
  }
}

function selectNode(n) {
  selected = n;
  restyle(); drawEdges();
  if (n.level !== "l1") zoomTo(n);
  const m = n.metrics || {};
  const findings = (n.finding_ids || []).map((id) => ({ id, ...findingsById[id] })).filter((f) => f.title);
  findings.sort((a, b) => (a.status === "confirmed" ? 0 : 1) - (b.status === "confirmed" ? 0 : 1));
  const props = n.proposed_changes || [];
  detail.innerHTML = `
    <div class="panel-head"><h2>${esc(n.name)}</h2><span class="note">${esc(n.level.toUpperCase())}</span></div>
    <div class="panel-body">
      <p style="margin-top:0">${esc(n.role || "")}</p>
      ${(n.paths || []).length ? `<div class="fileref">${(n.paths || []).map(esc).join("<br/>")}</div>` : ""}
      ${n.level === "l3" ? `
        <table class="data" style="margin-top:10px"><tbody>
          <tr><td>lines of code</td><td class="num">${m.loc ?? "—"}</td></tr>
          <tr><td>commits touching</td><td class="num">${m.churn_commits ?? "—"}</td></tr>
          <tr><td>cyclomatic complexity (sum)</td><td class="num">${m.ccn_total ?? "—"}</td></tr>
          <tr><td>hotspot rank</td><td class="num">${m.best_hotspot_rank ? "#" + m.best_hotspot_rank : "—"}</td></tr>
        </tbody></table>` : ""}
      ${n.community_check ? `<p class="note" style="margin-top:10px"><b>graph community check:</b> ${esc(n.community_check)}</p>` : ""}
      ${props.length ? `<h3 style="font-size:12px;margin:14px 0 6px">Proposed changes</h3>` +
        props.map((p) => `<div class="quote"><b>${esc(p.op)}</b>${p.target ? " → " + esc(p.target) : ""}: ${esc(p.rationale || "")} ${p.finding_id ? `<span class="fileref">(${esc(p.finding_id)})</span>` : ""}</div>`).join("") : ""}
      ${findings.length ? `<h3 style="font-size:12px;margin:14px 0 6px">Findings (${findings.length})</h3>` +
        findings.map((f) => `<div style="margin:0 0 9px">
            ${sevChip(f.severity)} ${statusChip(f.status)}
            <a href="findings-dashboard.html#${esc(f.id)}" style="display:block;margin-top:3px">${esc(f.id)}: ${esc(f.title)}</a>
          </div>`).join("") : ""}
    </div>`;
}

// ---------- proposed toggle & search ----------
modeBtn.addEventListener("click", () => {
  proposedMode = !proposedMode;
  modeBtn.setAttribute("aria-pressed", String(proposedMode));
  modeBtn.textContent = `proposed changes: ${proposedMode ? "on" : "off"}`;
  restyle();
});
search.addEventListener("input", () => {
  const q = search.value.trim().toLowerCase();
  for (const n of l3) {
    const hit = q && (n.name.toLowerCase().includes(q) || (n.paths || []).some((p) => p.toLowerCase().includes(q)));
    n._rect.setAttribute("fill", hit ? "var(--accent-soft)" : "var(--surface)");
  }
});

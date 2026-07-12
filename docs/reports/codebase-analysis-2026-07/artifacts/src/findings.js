// Findings dashboard: every finding with its full audit trail (mechanical
// evidence check -> adversarial verifier verdict), filterable; charts put the
// congestion story in one view (churn x complexity hotspot quadrant).
import { scaleLinear } from "d3-scale";
import { el, svgEl, initTheme, tooltip, esc, sevChip, statusChip, SEV_ORDER, counts } from "./shared.js";

const { findings, cleanSlates, hotspots, metricsMeta } = window.DATA;
const tip = tooltip();

const topbar = el("div", { class: "topbar" });
topbar.append(el("div", { class: "brand" },
  el("div", { class: "eyebrow" }, "dangerousrobot.org · codebase analysis · 2026-07"),
  el("div", { class: "title" }, "Findings dashboard")));
initTheme(topbar);
document.body.append(topbar);
const wrap = el("div", { class: "wrap" });
document.body.append(wrap);

// ---------- KPI row ----------
const confirmed = findings.filter((f) => f.status === "confirmed");
const kpi = el("div", { class: "tiles", style: "margin-bottom:14px" });
kpi.innerHTML = `
  <div class="tile"><div class="k">findings raised</div><div class="v">${findings.length}</div><div class="d">by 16 analysts</div></div>
  <div class="tile"><div class="k">confirmed</div><div class="v">${confirmed.length}</div><div class="d">survived evidence grep + adversarial verifier</div></div>
  <div class="tile"><div class="k">high severity</div><div class="v">${confirmed.filter((f) => f.severity === "high").length}</div><div class="d">confirmed high</div></div>
  <div class="tile"><div class="k">rejected / downgraded</div><div class="v">${findings.filter((f) => f.status.startsWith("rejected")).length} / ${findings.filter((f) => f.verification?.downgraded).length}</div><div class="d">kept visible as audit trail</div></div>
  <div class="tile"><div class="k">clean-slate designs</div><div class="v">${cleanSlates.length}</div><div class="d">${cleanSlates.filter((s) => s.stress_test?.verdict === "adopt").length} adopt · ${cleanSlates.filter((s) => s.stress_test?.verdict === "adapt").length} adapt · ${cleanSlates.filter((s) => s.stress_test?.verdict === "reject").length} reject</div></div>`;
wrap.append(kpi);

// ---------- charts row ----------
const charts = el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:14px;margin-bottom:14px" });
wrap.append(charts);

function chartPanel(title, note, { full = false } = {}) {
  const p = el("div", { class: "panel" });
  p.innerHTML = `<div class="panel-head"><h2>${esc(title)}</h2><span class="note">${esc(note)}</span></div>`;
  const body = el("div", { class: "panel-body" });
  p.append(body);
  (full ? wrap : charts).append(p);
  return body;
}

// Hotspot quadrant: churn (x) vs complexity (y); top files labeled.
{
  const body = chartPanel("Congestion quadrant", "each dot = one source file · data: metrics.json hotspots_top30");
  const W = 460, H = 300, M = { t: 14, r: 16, b: 34, l: 44 };
  const xs = scaleLinear().domain([0, Math.max(...hotspots.map((h) => h.churn_commits)) * 1.06]).range([M.l, W - M.r]);
  const ys = scaleLinear().domain([0, Math.max(...hotspots.map((h) => h.ccn_total)) * 1.08]).range([H - M.b, M.t]);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, style: "width:100%;display:block" });
  for (const t of xs.ticks(5)) {
    svg.append(svgEl("line", { x1: xs(t), x2: xs(t), y1: M.t, y2: H - M.b, stroke: "var(--grid)" }));
    const lb = svgEl("text", { x: xs(t), y: H - M.b + 16, fill: "var(--muted)", "font-size": 10.5, "text-anchor": "middle", class: "monolabel" });
    lb.textContent = t; svg.append(lb);
  }
  for (const t of ys.ticks(5)) {
    svg.append(svgEl("line", { y1: ys(t), y2: ys(t), x1: M.l, x2: W - M.r, stroke: "var(--grid)" }));
    const lb = svgEl("text", { x: M.l - 6, y: ys(t) + 3, fill: "var(--muted)", "font-size": 10.5, "text-anchor": "end", class: "monolabel" });
    lb.textContent = t; svg.append(lb);
  }
  const xl = svgEl("text", { x: (M.l + W - M.r) / 2, y: H - 6, fill: "var(--ink-2)", "font-size": 10.5, "text-anchor": "middle" });
  xl.textContent = "commits touching file (churn)"; svg.append(xl);
  const yl = svgEl("text", { x: 12, y: (M.t + H - M.b) / 2, fill: "var(--ink-2)", "font-size": 10.5, "text-anchor": "middle", transform: `rotate(-90 12 ${(M.t + H - M.b) / 2})` });
  yl.textContent = "cyclomatic complexity (sum)"; svg.append(yl);
  for (const h of hotspots) {
    const r = 4 + 9 * Math.sqrt(h.betweenness_sum / (hotspots[0].betweenness_sum || 1));
    const c = svgEl("circle", { cx: xs(h.churn_commits), cy: ys(h.ccn_total), r, fill: "var(--s1)", opacity: 0.65, stroke: "var(--surface)", "stroke-width": 1.5 });
    c.addEventListener("mousemove", (ev) => tip.show(
      `<div class="tip-title mono">${esc(h.path)}</div>
       <div class="tip-sub">rank #${h.rank} · churn ${h.churn_commits} · ccn ${h.ccn_total} · centrality ${h.betweenness_sum.toFixed(3)}</div>`, ev.clientX, ev.clientY));
    c.addEventListener("mouseleave", () => tip.hide());
    svg.append(c);
    if (h.rank <= 3) {
      const t = svgEl("text", { x: xs(h.churn_commits), y: ys(h.ccn_total) - r - 4, fill: "var(--ink)", "font-size": 10.5, "text-anchor": "middle", class: "monolabel" });
      t.textContent = h.path.split("/").pop(); svg.append(t);
    }
  }
  body.append(svg);
  body.append(el("p", { class: "note", style: "margin:6px 0 0" }, "dot size = graph betweenness centrality (how much of the system routes through the file). Top-right = the congestion zone: complex AND frequently changed."));
}

// Findings by subsystem x severity (confirmed only)
{
  const body = chartPanel("Confirmed findings by subsystem", "severity uses the fixed status palette · labels on bars");
  const bySub = new Map();
  for (const f of confirmed) {
    if (!bySub.has(f.subsystem)) bySub.set(f.subsystem, { high: 0, medium: 0, low: 0 });
    bySub.get(f.subsystem)[f.severity]++;
  }
  const items = [...bySub.entries()].sort((a, b) => (b[1].high * 100 + b[1].medium * 10 + b[1].low) - (a[1].high * 100 + a[1].medium * 10 + a[1].low));
  const W = 460, ROW = 21, M = { l: 158, r: 30 };
  const maxN = Math.max(...items.map(([, c]) => c.high + c.medium + c.low));
  const xs = scaleLinear().domain([0, maxN]).range([0, W - M.l - M.r]);
  const H = items.length * ROW + 26;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, style: "width:100%;display:block" });
  const COLORS = { high: "var(--critical)", medium: "var(--serious)", low: "var(--warning)" };
  items.forEach(([sub, c], i) => {
    const y = i * ROW + 6;
    const lb = svgEl("text", { x: M.l - 8, y: y + 10, fill: "var(--ink-2)", "font-size": 11, "text-anchor": "end", class: "monolabel" });
    lb.textContent = sub; svg.append(lb);
    let x = M.l;
    for (const sev of ["high", "medium", "low"]) {
      if (!c[sev]) continue;
      const w = Math.max(2, xs(c[sev]) - 2);
      const rect = svgEl("rect", { x, y, width: w, height: 13, rx: 3, fill: COLORS[sev] });
      rect.addEventListener("mousemove", (ev) => tip.show(`<div class="tip-title">${esc(sub)}</div><div class="tip-sub">${c[sev]} ${sev}</div>`, ev.clientX, ev.clientY));
      rect.addEventListener("mouseleave", () => tip.hide());
      svg.append(rect);
      x += xs(c[sev]);
    }
    const total = svgEl("text", { x: x + 5, y: y + 10, fill: "var(--muted)", "font-size": 10.5, class: "monolabel" });
    total.textContent = c.high + c.medium + c.low; svg.append(total);
  });
  body.append(svg);
  body.append(el("div", { class: "legend", style: "margin-top:6px" }));
  body.lastChild.innerHTML = `<span class="li"><span class="sw" style="background:var(--critical)"></span>high</span>
    <span class="li"><span class="sw" style="background:var(--serious)"></span>medium</span>
    <span class="li"><span class="sw" style="background:var(--warning)"></span>low</span>`;
}

// Clean-slate verdicts
{
  const body = chartPanel("Clean-slate designs, stress-tested", "each 'if rebuilt today' proposal was attacked by an independent skeptic", { full: true });
  const t = el("table", { class: "data" });
  t.innerHTML = `<thead><tr><th>subsystem</th><th>design</th><th>skeptic verdict</th><th>adapted proposal</th></tr></thead><tbody>
    ${cleanSlates.map((s) => `<tr>
      <td class="mono">${esc(s.subsystem)}</td>
      <td style="max-width:300px">${esc(s.title)}</td>
      <td>${s.stress_test ? `<span class="chip ${s.stress_test.verdict === "adopt" ? "st-confirmed" : s.stress_test.verdict === "reject" ? "st-rejected" : "sev-low"}"><span class="dot"></span>${esc(s.stress_test.verdict)}</span>` : "—"}</td>
      <td style="max-width:380px">${s.stress_test?.verdict === "adapt" && s.stress_test.simpler_alternative
        ? `<details><summary style="cursor:pointer;font-weight:650;color:var(--accent)">view adaptation</summary><p style="margin:6px 0 0;color:var(--ink-2)">${esc(s.stress_test.simpler_alternative)}</p></details>`
        : "—"}</td>
    </tr>`).join("")}</tbody>`;
  body.append(el("div", { style: "overflow-x:auto" }, t));
}

// ---------- filters + list ----------
const listPanel = el("div", { class: "panel" });
wrap.append(listPanel);
const cats = [...counts(findings, "category").keys()].filter(Boolean).sort();
const subs = [...counts(findings, "subsystem").keys()].filter(Boolean).sort();
const statuses = [...counts(findings, "status").keys()].filter(Boolean).sort();
const mkSel = (label, opts) => {
  const s = el("select", { "aria-label": label });
  s.innerHTML = `<option value="">${esc(label)}: all</option>` + opts.map((o) => `<option>${esc(o)}</option>`).join("");
  return s;
};
const fSev = mkSel("severity", ["high", "medium", "low"]);
const fCat = mkSel("category", cats);
const fSub = mkSel("subsystem", subs);
const fSt = mkSel("status", statuses);
fSt.value = "confirmed";
const fQ = el("input", { type: "search", placeholder: "search text…", "aria-label": "Search findings" });
const head = el("div", { class: "panel-head" });
head.append(el("h2", {}, "All findings"), el("div", { class: "spacer" }),
  el("div", { class: "controls" }, fSev, fCat, fSub, fSt, fQ));
listPanel.append(head);
const listBody = el("div", { class: "panel-body" });
listPanel.append(listBody);

function card(f) {
  const ev = (f.evidence || []).filter((e) => (f.evidence_check || []).find((c) => c.file === e.file && c.ok) || !(f.evidence_check || []).length);
  return `<article id="${esc(f.id)}" style="padding:12px 4px;border-bottom:1px solid var(--grid)">
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <code style="color:var(--muted)">${esc(f.id)}</code>
      ${sevChip(f.severity)} ${statusChip(f.status)}
      <span class="chip"><span class="dot" style="background:var(--s5)"></span>${esc(f.category)}</span>
      <span class="chip"><span class="dot" style="background:var(--s1)"></span>${esc(f.subsystem)}</span>
      ${f.effort ? `<span class="chip"><span class="dot" style="background:var(--baseline)"></span>effort: ${esc(f.effort)}</span>` : ""}
    </div>
    <h3 style="margin:7px 0 4px;font-size:14px">${esc(f.title)}</h3>
    ${f.current ? `<p style="margin:4px 0"><b>Current:</b> ${esc(f.current)}</p>` : ""}
    ${f.proposed ? `<p style="margin:4px 0"><b>Move toward:</b> ${esc(f.proposed)}</p>` : ""}
    ${f.migration ? `<p style="margin:4px 0" class="note"><b>Migration:</b> ${esc(f.migration)}</p>` : ""}
    ${f.verification ? `<p style="margin:4px 0" class="note"><b>Verifier${f.verification.downgraded ? " (downgraded from " + esc(f.original_severity) + ")" : ""}:</b> ${esc(f.verification.note || f.verification.verdict)}${f.verification.simpler_alternative ? `<br/><b>Simpler alternative:</b> ${esc(f.verification.simpler_alternative)}` : ""}</p>` : ""}
    ${ev.length ? `<details><summary class="fileref" style="cursor:pointer">evidence (${ev.length})</summary>
      ${ev.map((e) => `<div class="quote">${esc(e.quote)}<br/><span class="fileref">${esc(e.file)}:${esc(e.line)}</span></div>`).join("")}</details>` : ""}
  </article>`;
}

function render() {
  const q = fQ.value.trim().toLowerCase();
  let list = findings.filter((f) =>
    (!fSev.value || f.severity === fSev.value) &&
    (!fCat.value || f.category === fCat.value) &&
    (!fSub.value || f.subsystem === fSub.value) &&
    (!fSt.value || f.status === fSt.value) &&
    (!q || JSON.stringify(f).toLowerCase().includes(q)));
  list = list.sort((a, b) => (SEV_ORDER[a.severity] ?? 3) - (SEV_ORDER[b.severity] ?? 3) || a.id.localeCompare(b.id));
  listBody.innerHTML = list.length
    ? `<p class="note" style="margin:0 0 4px">${list.length} finding(s)</p>` + list.map(card).join("")
    : `<p class="note">Nothing matches these filters.</p>`;
}
[fSev, fCat, fSub, fSt].forEach((s) => s.addEventListener("change", render));
fQ.addEventListener("input", render);
render();

// deep-link (#FINDING-ID): clear status filter so the target is visible
if (location.hash) {
  fSt.value = "";
  render();
  const t = document.getElementById(location.hash.slice(1));
  if (t) { t.scrollIntoView({ block: "center" }); t.style.background = "color-mix(in srgb, var(--accent) 8%, transparent)"; }
}

wrap.append(el("p", { class: "note", style: "margin-top:14px" },
  `Provenance: metrics computed at commit ${metricsMeta.commit.slice(0, 8)} (${metricsMeta.tools}); findings pipeline: 16 analysts → mechanical quote-grep → 16 refute-minded verifiers → 13 clean-slate skeptics. Rejected findings stay listed (filter status) as the audit trail.`));

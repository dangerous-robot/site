// Shared runtime for the analysis artifacts: theme toggle, tooltip, tiny helpers.
// Data is injected by generate-artifacts.mjs as window.DATA.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function svgEl(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

export function initTheme(topbar) {
  const root = document.documentElement;
  const btn = el("button", { class: "btn", "aria-label": "Toggle color theme" }, "theme");
  btn.addEventListener("click", () => {
    const dark = root.getAttribute("data-theme") === "dark" ||
      (!root.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
    root.setAttribute("data-theme", dark ? "light" : "dark");
  });
  topbar.append(btn);
}

let tipNode;
export function tooltip() {
  if (!tipNode) {
    tipNode = el("div", { class: "tip", role: "tooltip" });
    document.body.append(tipNode);
  }
  return {
    show(html, x, y) {
      tipNode.innerHTML = html;
      tipNode.style.display = "block";
      const r = tipNode.getBoundingClientRect();
      tipNode.style.left = Math.min(x + 14, innerWidth - r.width - 10) + "px";
      tipNode.style.top = Math.min(y + 14, innerHeight - r.height - 10) + "px";
    },
    hide() { tipNode.style.display = "none"; },
  };
}

export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export const SEV_ORDER = { high: 0, medium: 1, low: 2 };
export const sevChip = (sev) =>
  `<span class="chip sev-${esc(sev)}"><span class="dot"></span>${esc(sev)}</span>`;
export const statusChip = (st) =>
  `<span class="chip st-${esc(st)}"><span class="dot"></span>${esc(st)}</span>`;

export function counts(arr, key) {
  const m = new Map();
  for (const x of arr) {
    const k = typeof key === "function" ? key(x) : x[key];
    m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}

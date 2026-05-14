# A11y Do-Now: WCAG 2.1 AA Blockers

Audit date: 2026-05-13  
Pages audited: `/` (87), `/resources` (92), `/research` (92)  
Tool: Lighthouse 13.3.0 accessibility category + manual source review

---

## 1. `aria-prohibited-attr` — Homepage only · WCAG 4.1.2

**What:** JavaScript at `src/pages/index.astro:981` sets `aria-label` on `.hero-title__word` `<span>` elements to preserve readable text while the glitch animation replaces `innerHTML` with individual letter spans. `aria-label` is prohibited on elements with implicit role `generic` (`<span>`).

**Fix:** Replace the `aria-label` setAttribute with a visually-hidden span:

```js
// Before (line 981):
word.setAttribute('aria-label', text);
word.innerHTML = Array.from(text).map(
  (ch) => '<span class="hero-title__letter" aria-hidden="true">' + ch + '</span>'
).join('');

// After:
word.innerHTML =
  '<span class="sr-only">' + text + '</span>' +
  Array.from(text).map(
    (ch) => '<span class="hero-title__letter" aria-hidden="true">' + ch + '</span>'
  ).join('');
```

Also add `.sr-only` to `src/styles/global.css` (currently only defined per-component):

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}
```

---

## 2. Color contrast: alpha-banner — All pages · WCAG 1.4.3

**What:** `.alpha-tag` "BETA RELEASE" text uses `color: var(--color-surface)` (`#212226`) on `background: var(--color-accent)` (`#42958b`) in dark mode. Ratio ≈ 4.46:1; threshold is 4.5:1 for normal text (12px bold does not qualify as large text).

**Fix:** In `src/layouts/Base.astro`, change the banner text token from `--color-surface` to `--color-bg`:

```css
/* Before */
.alpha-banner {
  background: var(--color-accent);
  color: var(--color-surface);   /* #212226 in dark → 4.46:1 */
}

/* After */
.alpha-banner {
  background: var(--color-accent);
  color: var(--color-bg);        /* #19191b in dark → 4.95:1 ✓ */
}
```

Light mode is unaffected: text color becomes `#f8f7f4` (near-white) against the teal `#287870` background, giving ~4.88:1.

---

## 3. Color contrast: footer text and links — All pages · WCAG 1.4.3

**What:** Footer text and links fail contrast in dark mode; footer text also fails in light mode. Lighthouse only ran in dark mode (`:root` defaults to dark).

| Token | Value | Background | Ratio | Required |
|---|---|---|---|---|
| `--color-footer-text` (dark) | `#707083` | `#19191b` | 3.62:1 | 4.5:1 |
| `--color-footer-link` (dark) | `#7a7a8e` | `#19191b` | 4.18:1 | 4.5:1 |
| `--color-footer-text` (light) | `#9090a0` | `#f8f7f4` | 2.93:1 | 4.5:1 |
| `--color-footer-link` (light) | `#6c6c80` | `#f8f7f4` | 4.79:1 | 4.5:1 — passes, no change needed |

**Fix:** In `src/styles/tokens.css`, adjust three tokens (light-mode link passes and stays):

```css
/* Dark theme — current → suggested */
--color-footer-text: #707083;  →  #8a8a98;   /* 5.16:1 on #19191b */
--color-footer-link: #7a7a8e;  →  #8a8a9e;   /* 5.19:1 on #19191b */

/* Light theme — current → suggested (darker = more contrast on near-white bg) */
--color-footer-text: #9090a0;  →  #606070;   /* 5.76:1 on #f8f7f4 */
/* --color-footer-link: #6c6c80 — no change, 4.79:1 passes */
```

Ratios above are calculated via the WCAG relative luminance formula, not estimated.

---

## 4. Color contrast: eyebrow labels — `/resources`, `/research` · WCAG 1.4.3

**What:** Small uppercase eyebrow labels use `color: var(--color-text-faint)` (`#707083`) which fails in both locations:

- `.site-section-eyebrow` in nav on `--color-surface` (`#212226`) → ~3.27:1
- `.eyebrow` in page hero on `--color-bg` (`#19191b`) → ~3.62:1

Sources: `src/layouts/Base.astro:301`, `src/styles/resources.css:96`, `src/pages/research/index.astro:390`.

**Fix:** Use `--color-text-muted` (`#9a9aa8`) instead of `--color-text-faint`:

- On `#212226`: ~6.2:1 ✓
- On `#19191b`: ~4.8:1 ✓
- Light mode (`#5c5c6e` on `#ffffff`): ~6.5:1 ✓

Change `color: var(--color-text-faint)` to `color: var(--color-text-muted)` in those three selectors only.

> **Do NOT change the `--color-text-faint` token value.** It has 50+ usages across the codebase (tables, badges, metadata, decorative labels) where the lower contrast is appropriate or where the surrounding background provides sufficient contrast. Only the three eyebrow selectors above are in scope.

> **Nav change coordination:** Another agent is modifying navigation structure. Confirm `.site-section-eyebrow` still exists after those changes before applying this fix.

> **Adjacent issue:** `src/styles/resources.css:217` (`.pill-nav-wrap .resources-pill-nav-label`) also uses `--color-text-faint` at the same size. Not flagged by the audited pages but worth checking on resource detail pages.

---

## 5. Links rely on color only — All pages, footer · WCAG 1.4.1

**What:** Footer `<a>` elements have `text-decoration: none` and are distinguishable from surrounding text only by color. Lighthouse flagged three links (treadlightly.ai, GitHub, CC license) as relying on color alone within a text block.

Source: `src/layouts/Base.astro:392–395`.

**Fix:**

```css
/* Before */
.site-footer a {
  color: var(--color-footer-link);
  text-decoration: none;
}

/* After */
.site-footer a {
  color: var(--color-footer-link);
  text-decoration: underline;
  text-underline-offset: 2px;
}
```

---

## Post-implementation checklist

- [x] **Issue 1** — VoiceOver confirmed: h1 announces as "Dangerous Robot" cleanly. No double-read.
- [ ] **Issue 5** — Hover state on `.site-footer a` inherits `text-decoration: underline` from the default rule. Explicit `text-decoration` on `:hover` was added for safety, since nav rules above use `text-decoration: none` on hover.
- [x] **Light-mode audit** — Calculated via WCAG luminance formula across all token pairs on the three audited pages. All fixed tokens pass:
  - Alpha-banner text: 4.89:1 ✓
  - Nav links: 5.13:1 ✓
  - Eyebrow (muted): 6.10–6.54:1 ✓
  - Footer text (fixed): 5.76:1 ✓
  - Footer link (unchanged): 4.79:1 ✓
  - Body/muted text: all ≥ 6:1 ✓

  **Pre-existing, out-of-scope:** `--color-text-faint: #9090a0` fails at 2.93:1 in light mode (same token fails at 3.62:1 in dark mode; 50+ usages, not caught by Lighthouse). Chips use this token as a fallback color and also fail. Flagged as follow-on work.

---

## Not blocking AA (notes)

- **`.research-index__num` contrast** (`/research`): decorative sequence numbers with `aria-hidden="true"`. Exempt from 1.4.3 as decorative text. Removing `opacity: 0.8` would improve visual quality without a compliance obligation.
- **Skip navigation link**: `bypass` audit was N/A (not flagged). A skip link is recommended for keyboard users; not strictly required until repeated nav blocks trigger the criterion.
- **Focus indicators**: `:focus-visible` in `global.css` uses `--color-accent` (~4.95:1 on dark bg). Passes 2.4.7.
- **Heading order**: Passes on all three pages.
- **`html[lang]`**: Passes. Lang attribute is present and valid.

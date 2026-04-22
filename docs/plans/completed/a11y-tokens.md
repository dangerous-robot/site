# Plan: CSS token system + accessibility control

## Goals

1. Replace hardcoded hex colors with semantic CSS custom properties.
2. Light/dark/system theme + high-contrast overlay, persisted in localStorage, no flash of wrong theme.
3. Self-contained `A11yControl` FAB for theme, contrast, and font-size selection.
4. Stable token vocabulary for the entity-views plan to build on.

## Token categories

Definitions live in `src/styles/tokens.css`. Broad categories:

- **Color**: `--color-bg`, `--color-surface`, `--color-text`, `--color-text-muted`, `--color-text-faint`, `--color-accent`, `--color-border`, `--color-on-badge`, plus nav/footer/FAB/popover/radio-group surfaces.
- **Verdict semantic**: `--color-verdict-{true,mostly-true,mixed,mostly-false,false,unverified}`. Per-theme variants for legibility.
- **Source kind semantic**: `--color-kind-{report,article,documentation,dataset,blog,video,index}`. Kind colors don't vary by contrast mode.
- **Layout**: `--content-max-width` (48rem; overridable per-page).
- **Typography**: `--font-body`, `--font-heading`, `--font-mono`, `--line-height-body`, `--line-height-heading`, `--font-size-{base,sm,xs,2xs}`.
- **Spacing**: `--space-{xs,sm,md,lg,xl,2xl}`.
- **Radius / shadow**: `--radius-{sm,md,full}`, `--shadow-{fab,popover}`.

## Palette rationale

Accent is a muted teal — plausible for an environmental-transparency project without being greenwashed bright green, and AA-contrast against both dark and light backgrounds. The dark bg has a slight blue undertone (`#111112`) rather than flat black; the light bg is a warm off-white (`#f8f7f4`) rather than stark white. Exact values live in `tokens.css`.

## Theme / contrast matrix

`data-theme` and `data-contrast` are orthogonal. High-contrast is an additional `[data-contrast="high"]` selector block, no logic branching. Four combinations:

| `data-theme` | `data-contrast` | Result |
|---|---|---|
| `dark` | `normal` | Default dark |
| `dark` | `high` | Black/white/bright teal, AAA |
| `light` | `normal` | Warm-white |
| `light` | `high` | White/black/dark teal, AAA |

`theme="system"` resolves to `light` or `dark` via `prefers-color-scheme` and tracks changes live.

## Font treatment

System fonts only — no self-hosted webfont. Keeps the build simple and avoids FOUT.

- Body: `system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`
- Headings: `Georgia, "Times New Roman", Times, serif`

Flair: a 2px accent left-border on the site name (`border-left: 2px solid var(--color-accent); padding-left: 0.5rem`).

## A11y control behavior

**Placement**: bottom-left FAB, `position: fixed`, `z-index: 200`. Matches the parallax-ai reference; primary content and CTAs live top/right.

**Popover (≥640px)**: opens above the FAB, 240px wide, three sections — Contrast (2), Theme (3), Text size (3).

**Bottom sheet (<640px)**: full-width sheet anchored to the bottom; slides up with a translateY transition. Dismissible by ESC, FAB re-tap, or backdrop tap.

**Keyboard**: FAB is a `<button>` with `aria-label` + `aria-expanded`. Popover is `role="dialog" aria-modal="true"` with a focus trap. Arrow keys navigate within each `role="radiogroup"`; Enter/Space activate; ESC closes; focus returns to the FAB.

**Flash prevention**: an inline synchronous `<script>` in `<head>` reads localStorage and sets `data-theme`/`data-contrast`/`data-font-size` on `<html>` before CSS paints. `localStorage` reads are wrapped in try/catch so private-mode throws don't block the rest of the head.

**Motion**: all transitions gated behind `@media (prefers-reduced-motion: no-preference)`. Static states remain correct when motion is disabled.

## Mobile-first adaptations

- Touch targets ≥44×44px on mobile.
- `@media (max-width: 639px)` swaps popover for full-width bottom sheet.
- FAB respects `env(safe-area-inset-bottom)`.
- No horizontal scroll at 320px.

## Coupled code across the pre-paint and component scripts

The pre-paint inline script in `Base.astro` and the client script in `A11yControl.astro` both encode the same three localStorage keys (`dr-theme`, `dr-contrast`, `dr-font-size`) and the same font-size map (`small=16px`, `medium=18px`, `large=20px`). This cannot be deduplicated because the pre-paint script must be inline and cannot import a module. Both files carry a comment noting the coupling; change them together.

## Contract with entity-views.md

**Overridable tokens**:
- `--content-max-width` — entity-views sets this to `72rem` on list/matrix page wrappers via a `wide` prop or scoped selector. Do not modify the token globally.
- `--color-verdict-*` and `--color-kind-*` — use in extracted `VerdictBadge.astro` and `SourceRow.astro`. Do not hand-roll color maps in page frontmatter.

**Off-limits**:
- Don't modify existing tokens in `tokens.css`; add new ones via PR if needed.
- Don't modify the pre-paint inline script; theme init must stay synchronous.
- Don't add component-specific styles to `global.css`; use component `<style>` blocks.

**Safe to change**:
- Nav content and structure in `Base.astro`.
- `<A11yControl />` is nav-independent.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (cursory review) | completed-check | Added review history section; no unfinished work found |

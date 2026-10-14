# Plan: Design mockups tied to plans

**Status**: reviewed; not scheduled. Needs `release-triage` before M2 (it adds code under `scripts/`).
**Last updated**: 2026-10-09

Goal, in Brandon's words: "rigid and automated, where possible. I don't want claude to ask me what to do, I want the system to know what is needed. And of course always choose simplicity where you can."

## Status checklist

- [ ] M1: check that a canvas artboard can use the site's `tokens.css`
- [ ] M2: `scripts/design/mockup.py` with tests
- [ ] M3: the release gate requires a `Mockup` line on page plans
- [ ] M4: `design-mockup` skill, and AGENTS.md
- [ ] M5: move the SITE-J (Responsible AI chatbots) mockup onto tokens, pushed by the skill

## How it works

| Rule | What it means |
|---|---|
| Page plans get a mockup | A plan with a `**Page**:` header line (the page it changes) must also have a `**Mockup**:` line: the canvas URL. No `**Page**:` line, no mockup. Nobody decides case by case. |
| The repo holds the files | Artboards live in `docs/mockups/<plan-name>/project/` (`canvas.json` plus `*.dc.html`), committed. The canvas on claude.ai is a published copy. |
| Site tokens, not color values | Each push copies `src/styles/tokens.css` into the mockup folder (git-ignored copy). Artboards link it and use `var(--…)`, so a mockup shows the current site colors, fonts and spacing. A color value in an artboard's styles fails the push. |
| The plan is the spec | A mockup is never copied into `.astro` files. What a feedback round decides is written into the plan in the same commit as the mockup change, with one review-history row per round. |
| Sample data is labeled | Every mockup carries "Mockup: sample data, not findings" and uses placeholders for facts it does not have. |

Out of scope: Claude Design projects and their sync tool. They hold a component library, while this site needs page mockups tied to a plan.

## Who does what

Only a Claude session can publish to or read from a canvas (the Artifact tool); there is no command line or CI path. So the script does every step that has one right answer, and Claude makes the calls it prints.

| Step | Trigger | Done by |
|---|---|---|
| Require a mockup | `work_item.py start` for a plan with a `**Page**:` line | Gate, automatically (M3) |
| Create the canvas | Gate refusal names `design-mockup new <plan>` | Skill |
| Push | Any change under `docs/mockups/<plan-name>/`, or Brandon's feedback | Skill: read the canvas, ingest any hand edits, write decisions back, publish |

Brandon's part: look at the canvas and give feedback, or edit it in the canvas editor. Nothing else.

## Steps

### M1: tokens on a canvas
Publish a scratch canvas whose artboard has `<link rel="stylesheet" href="./tokens.css">` after the `support.js` line, `tokens.css` sent as a support file under `project/`, and one box styled `background: var(--color-bg, red)`.

Verify: Brandon answers one question: is the box red? Red means the stylesheet did not load. (The canvas instructions forbid agents rendering it themselves.)

If it fails: `prepare` writes a build copy with every `var(--x)` replaced by its dark-theme value and publishes that. The repo copy keeps the `var()` names.

### M2: `scripts/design/mockup.py`
Plain Python, standard library only. Add `docs/mockups/*/project/tokens.css` to `.gitignore`.

| Command | Does |
|---|---|
| `check-plan <plan>` | Exit 1 when the plan has a `**Page**:` header line and no `**Mockup**:` line with a `claude.ai` URL. |
| `ingest <plan> <saved-file>...` | Copies files saved by an Artifact read (scratchpad) into the mockup folder at their `project/` paths; prints `git diff --stat` for the folder. |
| `prepare <plan>` | Reads the canvas URL from the plan, copies `tokens.css` in, fails on any color value (`#hex`, `rgb()`, `rgba()`, `hsl()`) inside a `style` attribute or `<style>` block of an artboard, and prints the Artifact publish arguments (`url`, `root`, `file_path`, `files`) as JSON. Every file is sent each time; a mockup has few files. |

Verify: `python3 -m pytest scripts/design/test_mockup.py`, added to `inv check`. Fixture plans in `scripts/design/fixtures/`: `page-no-mockup.md` fails; `page-with-mockup.md` and `no-page.md` pass. `prepare` rejects `color:#4e4e5a` and `rgba(0,0,0,0.5)` in a style, accepts `href="#add"` and `&#160;`, and prints valid JSON. `ingest` maps a saved path to the right `project/` path. Positive control: `check-plan docs/plans/completed/responsible-ai-chatbots-claims.md` passes.

### M3: gate check
`work_item.py start` runs `check-plan` on `--plan`, and on `--section` too when the roadmap item links a plan file. On failure it refuses and prints: "This plan changes a page and has no Mockup line. Run: design-mockup new <plan>." Hotfixes skip it.

AGENTS.md: add the `**Page**:` and `**Mockup**:` header rule to Plans & Backlog, and a row for the check under § Agent workflow tooling. Rule 5 (ask at commit time whether touched plans are complete) gains an exception: a mockup feedback write-back does not ask.

Verify: `start` with SITE-J's plan passes; with `page-no-mockup.md` it is refused; with `no-page.md` it passes.

### M4: `design-mockup` skill
`.claude/skills/design-mockup/SKILL.md`, two modes. Listed in AGENTS.md § Agent workflow tooling.

| Mode | Steps |
|---|---|
| `new <plan>` | Quickstart for a design, create the canvas (title: the plan's title), add the `**Mockup**:` line, build `Main.dc.html` from the plan, run `push`. |
| `push <plan>` | Read the canvas's `project/` files (a session must read before it can publish). `ingest` them; if anything changed, it was a hand edit on the canvas: write what it decides into the plan. Apply Brandon's feedback, if any, to the artboard and the plan. `prepare`, publish, commit mockup and plan together with one review-history row for the round. |

Fixed choices, so the skill never asks:

| Choice | Rule |
|---|---|
| Slice | At most 3 products or items and 2 rows of each kind the plan defines; include any item the plan treats differently (for example a capped product) |
| Interactions | Build every interaction the plan specifies for the slice; start one open so a still view shows it |
| Theme | Dark only, until a plan asks for more |
| Copy | Plan wording first; `docs/decisions.md` copy rules; placeholders for anything else |
| A color with no token | Use the nearest token; list the substitution in that round's review-history row |

Verify: run `new` on `scripts/design/fixtures/page-no-mockup.md` (copied to a scratch plan) in a fresh session; it finishes with zero questions to Brandon and a committed mockup folder. Then edit the canvas by hand and run `push`; the edit lands in the repo and the plan.

### M5: first real use
Replace the color values in `docs/mockups/responsible-ai-chatbots-claims/project/Main.dc.html` with token names (nearest token where none matches: `#4e4e5a`, `#5fb3a8`, `#1c2120` and one `rgba()` today), then `design-mockup push docs/plans/completed/responsible-ai-chatbots-claims.md`.

Verify: `prepare` passes the color check, and a script check confirms each replaced exact-match value equals its token's dark value.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-09 | agent (claude-opus-5-5) | design | First draft, after the SITE-J mockup (v1, v2) was built by hand. |
| 2026-10-09 | agent (claude-opus-5-5), fresh-eyes review | design, iterated | The trigger is the `**Page**:` header line, not file names in the text (the text grep matched 25 completed plans). `pull` folded into `push`, which always reads first (the tool refuses a publish before a read). Gate also checks `--section`; rule 5 exception; `.gitignore` entry; tests with fixtures in `inv check`; color check limited to styles and widened to `rgb`/`hsl`; red-fallback M1 check; one review-history row per round; AGENTS.md updates. |

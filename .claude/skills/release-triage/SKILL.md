---
name: release-triage
description: "Classify a proposed code change against VERSION.md semver rules, decide which release it belongs to (the in-flight line, the next minor, the next major, or Unscheduled), update the roadmap or UNSCHEDULED.md accordingly, and register the active work item so the release gate allows edits. Use before any new feature, schema, or behavior change; when the user starts describing or coding work that is not in the active roadmap; or when the release gate denies an edit."
---

# Release triage

The repo has three mutually exclusive work states (AGENTS.md § Release planning): **Unscheduled** (`docs/UNSCHEDULED.md`), **Scheduled** (a release roadmap, `docs/v*.*.*-roadmap.md`), and **Plan-only** (`docs/plans/`). Only Scheduled work may be coded; the PreToolUse hook `scripts/release-gate/release_gate.py` enforces that by denying edits under `src/`, `pipeline/`, `workers/`, `scripts/`, `public/`, `.github/` and root build config unless `.claude/active-work.json` names a valid, scheduled item. Docs, plans, `research/`, and `src/content/` are never gated, so planning is always possible.

This skill is the judgment step. Do it in the conversation, with full context, then record the result. Keep it to one short exchange: the goal is "Great, this is a minor feature; I've put it in the next release so it doesn't widen the in-flight beta. Here is the plan outline", not a ceremony.

## Step 1: Read the state (no guessing)

```bash
python3 scripts/release-gate/work_item.py status
cat VERSION.md
sed -n '1,30p' docs/v*-roadmap.md          # header table of the active roadmap
grep -n '^## ' docs/UNSCHEDULED.md | head -40
ls docs/plans/ docs/plans/drafts/ 2>/dev/null
git status --short | head -20               # is other work in flight in this checkout?
```

If a work item is already active and the new request is the same work, stop here and continue implementing. If it is different work, say so and either finish the current item (`work_item.py finish`, after the AGENTS.md rules 4 to 6 updates) or ask which one the user wants active. One checkout has one active item.

## Step 2: Classify the change

Use the version semantics in `VERSION.md`, quoted here as of 2026-10-06 (re-read the file; it wins if it has changed):

| Kind | VERSION.md definition | Typical signals |
|---|---|---|
| `major` | Breaking change to verdict enum, criterion definitions, or entity URL structure | `src/content.config.ts` enum changes, `research/` schema migrations, URL slug or route renames |
| `minor` | New entity type, new criterion, new feature shipped | New page, component, `dr` command, Worker endpoint, new content collection field (additive) |
| `patch` | Content corrections, verdict updates, bug fixes, source additions | Bug fixes, copy, styling fixes, dependency bumps, test-only changes |

Pre-1.0 rule: while the working version is `1.0.0-beta.N`, VERSION.md says content, features and schema may still change within the beta line, and each deploy bumps N. So before 1.0.0, a `major` classification is a signal to **ask**, not an automatic bump to a new line; after 1.0.0 it always targets the next major roadmap.

Also classify **size**: `small` (fits in the current beta or patch without a plan file; a roadmap work item or a checklist line is enough) versus `planned` (needs a sub-plan under `docs/plans/`). Anything touching more than a handful of files, or any new feature, is `planned`.

## Step 3: Decide the release

Decision rules, in order:

1. **patch** → the active release line (the roadmap named in `VERSION.md` "Active release:"). Add it as a new work item (next unused letter, topic prefix) under `## Scheduled`, or as a checklist line in an existing item it belongs to. Small patches go straight to registration.
2. **minor, and the active line is a pre-1.0 beta** → ask one question: "Ride the current beta line (next beta.N) or hold for after 1.0.0?" Default recommendation: ride the beta line if it serves the current focus (`docs/mission-and-voice.md`, `docs/decisions.md`); otherwise hold.
3. **minor, post-1.0, and the active line is a patch release** → the next minor roadmap. If `docs/v{next-minor}-roadmap.md` does not exist, create it from the template below.
4. **major, post-1.0** → the next major roadmap, never the in-flight line. Create `docs/v{next-major}-roadmap.md` if absent. Say explicitly that it is parked there so it does not conflict with the in-flight release.
5. **Does not serve the current focus** (check `docs/mission-and-voice.md` and `docs/decisions.md`) → Unscheduled. Add it to `docs/UNSCHEDULED.md` with a one-line `Target: vX.Y.Z` note and **do not register a work item**. Planning (brainstorming, a draft plan) is still allowed because `docs/` is not gated; code is not.

When creating a new roadmap file, follow AGENTS.md naming (`docs/v{semver}-roadmap.md`) and AGENTS.md roadmap layout (IDs like `SITE-J`: topic prefix plus the next unused letter; cite as "SITE-J (name)"). Use this minimal skeleton; do not pre-fill items you have not decided:

```markdown
# v{semver} Roadmap

**Status**: Planned, not started (the active line is {active roadmap})  
**Last updated**: YYYY-MM-DD  
**Working version**: n/a until this line becomes active (see `VERSION.md`)

Status key: `done` | `in progress` | `ready` | `plan needed` | `decision needed` | `deferred`

## Releases

| Release | Contents | State |
|---|---|---|
| `{semver}` | {PREFIX}-A ({short name}) | Not started |

## Plan

- **{semver}:** {PREFIX}-A ({short name})

---

## Scheduled

### {PREFIX}-A. {Title}

**Status**: `plan needed`

{One paragraph: what and why. Link the plan once it exists.}
```

Do **not** change `VERSION.md` "Active release:" when creating a future roadmap. The active line changes only when the current release ships (AGENTS.md transition rules).

## Step 4: Propose, then confirm (one question)

Write a three-to-five line proposal and ask for a yes/no:

> **Triage:** "{title}" is a **{kind}** ({one-line reason, citing the VERSION.md rule}). The in-flight line is `{active release}` at `{working version}`. I propose scheduling it in **`{target roadmap}`** as {ID} ({name}) {or: as a line in {ID} ({name})} so it {does not widen the beta | does not conflict with the in-flight minor | lands with the patch}. Plan: {small: none needed | planned: draft at docs/plans/drafts/{name}.md via brainstorming → writing-plans}. OK?

If the user already stated the target release in their request, skip the question and state the decision instead.

## Step 5: Record it, then register

In this order, so the gate never passes work the docs do not show:

1. Roadmap or UNSCHEDULED.md edit per Step 3 (these paths are ungated). Keep AGENTS.md Plans & Backlog rule 6: moving an item into a roadmap removes it from `UNSCHEDULED.md`.
2. For `planned` work, run Superpowers **brainstorming** then **writing-plans**. Both write under `docs/plans/drafts/` in this repo (AGENTS.md § Agent workflow tooling), never `docs/superpowers/`.
3. Register:

```bash
# planned work
python3 scripts/release-gate/work_item.py start --title "{title}" --kind {kind} --release v{semver} --plan docs/plans/drafts/{name}.md
# small work listed directly in the roadmap
python3 scripts/release-gate/work_item.py start --title "{title}" --kind {kind} --release v{semver} --section "{ID} ({name})"
```

`start` refuses when the roadmap file or plan file does not exist. That is the point: fix the docs, not the command.

## Hotfix path

For a production break that cannot wait for triage:

```bash
python3 scripts/release-gate/work_item.py hotfix --title "{title}" --reason "{what is broken, where}"
```

It expires after 4 hours. A hotfix is a `patch`; add it to the active roadmap or `UNSCHEDULED.md` before `finish`. Do not use hotfix to skip triage on feature work; the record is visible in the session and the user will see it.

## Finishing

When the work lands (or the session ends mid-work and the user wants a clean slate):

```bash
python3 scripts/release-gate/work_item.py finish
```

Then apply AGENTS.md Plans & Backlog rules 4 to 6 (tick the plan, update the roadmap status with a commit ref, sync `UNSCHEDULED.md`) and rule 5 at commit time (ask whether touched plans are complete).

## Bending the gate (humans only)

- Turn it off for one session: launch with `RELEASE_GATE=off claude`.
- Widen or narrow what is gated: edit the lists at the top of `scripts/release-gate/release_common.py`.
- Change the hotfix window: `HOTFIX_TTL_HOURS` in the same file.
- Remove it entirely: delete the two hook entries in `.claude/settings.json`.

Known gap: the gate sees `Edit`/`Write`/`MultiEdit` tool calls only. A shell command that rewrites a file (`sed -i`, `cat >`) is not intercepted. Do not use the shell to route around the gate; if the gate is wrong, bend it as above.

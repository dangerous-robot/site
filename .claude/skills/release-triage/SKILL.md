---
name: release-triage
description: "Classify a proposed code change against VERSION.md semver rules, decide which release it belongs to (the in-flight line, the next minor, the next major, or Unscheduled), update the roadmap or UNSCHEDULED.md accordingly, and register the active work item so the release gate allows edits. Use before any new feature, schema, or behavior change; when the user starts describing or coding work that is not in the active roadmap; or when the release gate denies an edit. Also use to answer what to work on next (§ Choosing the next item) and to triage the backlog in docs/UNSCHEDULED.md against docs/priorities.md (§ Backlog triage): when a beta or release ships, when the priority order changes, or when asked."
---

# Release triage

The repo has three mutually exclusive work states (AGENTS.md § Release planning): **Unscheduled** (`docs/UNSCHEDULED.md`), **Scheduled** (a release roadmap, `docs/v*.*.*-roadmap.md`), and **Plan-only** (`docs/plans/`). Only Scheduled work may be coded; the PreToolUse hook `scripts/release-gate/release_gate.py` enforces that by denying edits under `src/`, `pipeline/`, `workers/`, `scripts/`, `public/`, `.github/` and root build config unless `.claude/active-work.json` names a valid, scheduled item. Docs, plans, `research/`, and `src/content/` are never gated, so planning is always possible.

This skill is the judgment step. Do it in the conversation, with full context, then record the result. Keep it to one short exchange: the goal is "Great, this is a minor feature; I've put it in the next release so it doesn't widen the in-flight beta. Here is the plan outline", not a ceremony.

Steps 1 to 5 handle a change someone asked for or a denied edit; § Choosing the next item and § Backlog triage are the other two uses (flow: AGENTS.md § Priorities).

## Step 1: Read the state (no guessing)

```bash
python3 scripts/release-gate/work_item.py status
cat VERSION.md
cat docs/priorities.md                      # ranked themes; rank decides what goes first
sed -n '1,30p' docs/v*-roadmap.md          # header, releases and ## Plan of the active roadmap
grep -n '^### \|^\*\*Status\*\*' docs/v*-roadmap.md   # each work item and its status
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
5. **Does not serve the current focus** (check `docs/mission-and-voice.md` and `docs/decisions.md`) → Unscheduled. Add it to `docs/UNSCHEDULED.md` with a one-line `Target: vX.Y.Z` note and a triage marker (format in the `UNSCHEDULED.md` header), and **do not register a work item**. Planning (brainstorming, a draft plan) is still allowed because `docs/` is not gated; code is not.

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

## Choosing the next item

Answers "what should I work on next?" with one item, its first step, and what Brandon must decide. It works from the files alone (Step 1 state), so any session gets the same answer, and changes nothing until N4.

**Rank** comes from `docs/priorities.md` ("How to read it").

**Release size.** The beta in progress is the `**Next beta (beta.N):**` line in the active roadmap's `## Plan`. Each entry is a work item, or one checklist line of a larger item, written as "SITE-J (Responsible AI chatbots): published-claim refresh trail". An entry is open until its item is `done` or its line is ticked. The beta's size is its number of open entries. It has room while the size is under 5, or beyond that when the agent judges it reasonable (small items, or a split that would hurt).

Stop at the first step that gives an answer:

- **N1. Finish what is started.** `work_item.py status` names an item, or a roadmap item is `in progress`: continue it. The record is shared by every session in the checkout (`UNSCHEDULED.md` "Release gate follow-ups"), so if another session registered the item, do not take it over: ask Brandon, or work in a worktree. Uncommitted docs edits alone are not a started item.
- **N2. Ship a finished beta.** The next-beta line has entries and none is open: the answer is "deploy beta.N" (Brandon's call).
- **N3. Pick one.** Candidates are the open entries on the next-beta line and, while the beta has room, open `## Scheduled` items not on it. Skip `decision needed` items and name each decision for Brandon. Take the highest-ranked; on a tie, prefer an entry on the line, then `ready` over `plan needed`, then roadmap order. Name for Brandon any `propose schedule` backlog item that ranks at or above the winner. No candidate: run § Backlog triage, then ask Brandon.
- **N4. Start it.** The first step is the winner's first unticked checklist line. If that line needs the item's own plan and its Status is `plan needed`, writing the plan is the step (brainstorming, then writing-plans; docs are not gated). If the winner is not on the next-beta line, ask Brandon once to add it, as the entry for that first step. Then register (Step 5), using that line's plan when it has one.

Answer in this form:

> **Next:** {ID (name)}, starting with {first step}. **Why:** rank {N} theme "{theme}"; beta.{M} has {n} open entries (guideline 5). **Brandon decides:** {each decision named above, or "nothing"}.

Also say whether § Backlog triage is due; the answer does not wait for it.

## Backlog triage

Gives each item in `docs/UNSCHEDULED.md` a marker: the priority theme it serves and what happens to it next (format in that file's header). Triage schedules nothing by itself.

**Run it** when a beta or release ships, when the order in `docs/priorities.md` changes, when N3 finds no candidate, or when Brandon asks.

1. Read the Step 1 state and approved issues: `gh issue list --label approved --state open`. If `gh label list` shows no `approved` label, report the label as missing, not "no approved issues".
2. Pick the items: those with no marker, approved issues not yet cited, and markers that disagree with `priorities.md` or the roadmap (the theme is gone, or the work is now a roadmap line). "Deferred plans" rows carry no marker; raise one's revival (AGENTS.md rule 8) only when a theme now covers it.
3. Set the marker's theme, then its next step, by the first rule that fits:
   1. A roadmap checklist line covers it: `in <ID>`.
   2. Shipped: remove it, citing the commit (AGENTS.md rule 6). Obsolete, or the same work as another item: `propose drop`, naming the other.
   3. Fails the focus test (AGENTS.md rule 8): `propose defer`.
   4. A roadmap item needs it: `propose schedule`. Also, when no open roadmap item ranks at or above its theme: `propose schedule` for the highest-ranked such items, only as many as the beta has room for.
   5. Otherwise: `keep`.

   Leave an item you have not examined unmarked.
4. Write the markers in one change. Then ask Brandon once, one line per `propose` marker: "item (section): proposal, reason". Apply each answer at once: schedule runs Steps 2 to 5 (the item leaves `UNSCHEDULED.md`), defer follows AGENTS.md rule 8, drop deletes the item, and no sets `keep (Brandon)`. Do not propose a `(Brandon)` item again unless its theme's rank changes.

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

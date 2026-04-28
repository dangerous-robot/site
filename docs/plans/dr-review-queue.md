# Plan: `dr review-queue`

**Status**: Phase 1 shipped (2026-04-27). Phase 2 (`c`/`r`/`b`/`e` actions, filters, polish) and Phase 3 (pluggable queue types) not yet started.

## Context

Today, the only path for an operator to discover claims awaiting human sign-off is a manual `git status` plus filename inspection, or waiting for the `published-without-review` lint to fail in CI after a claim has already been flipped to `published`. There is no forward-looking surface that says "here are the N claims whose research is complete and that are sitting at `status: draft` waiting for you to read and approve them."

The existing `dr review` command (`pipeline/orchestrator/cli.py:580-763`) records sign-off for a single claim by slug. It assumes the operator already knows what to review. `review-queue` fills the gap above it: discover the work, walk through it, hand each item to `dr review --approve` (or skip it) without leaving the terminal.

Relationship to [`operator-queue-batch-workflow_stub.md`](operator-queue-batch-workflow_stub.md): that v2 stub describes a broader queue-driven batch flow with multiple operator-facing intake files (`REVIEW_QUEUE.md`, `ONBOARD_QUEUE.md`, etc.). This plan is a narrower v1 slice — no new intake files, no batch dispatcher; just a CLI surface over claim files that already exist on disk. The two are compatible: the queue-discovery logic here can later become the `REVIEW_QUEUE.md` source for the v2 batch flow.

Per Brandon's requirements, the command must:
- Be useful non-interactively (CI consumption, scripting) via `--format text|json`
- Prioritize convenience for an operator at a terminal — `git add -p`-style single-key interactive loop, no TUI
- Land in small phases (Phase 1 ships a usable subset)
- Eventually support multiple queue types, but Phase 1 only covers "drafts awaiting publication"

## Goals & non-goals

**Goals**
- Phase 1: a single command that lists draft claims with completed research and walks an operator through them interactively
- Reuse existing `dr review --approve` for the actual sign-off (no new approval path)
- JSON output that CI / scripts can pipe to `jq`
- Architecture leaves room for additional queue types later without rewriting Phase 1

**Non-goals**
- No web UI (deferred indefinitely)
- No full-screen TUI / curses; scrolling terminal output only
- No replacement for in-pipeline checkpoints (`review_sources`, `review_disagreement`, `review_onboard`); those stay where they are
- No new approval semantics; `human_review.reviewed_at` written by existing `dr review` code path

## Queue selection (Phase 1: "publication" queue)

A claim is in the publication queue when **all** of these hold:
- File matches `research/claims/*/*.md`
- Frontmatter `status` is `draft` (or absent — legacy)
- `.audit.yaml` sidecar exists next to the claim (research is complete)
- Sidecar `human_review.reviewed_at` is null or missing (not yet approved)

Excludes:
- `published`, `archived` — already past the queue
- `blocked` — operator attention is needed but the action is "fix sources," not "approve"; surfaces today via `dr lint` and is a candidate for a future `--type=blocked` queue (see Phase 3)
- Drafts without a sidecar — research not yet run; surfaces via the pipeline itself

## Phasing

### Phase 1 — minimum viable queue

Ship a single command:

```
dr review-queue [--format text|json] [--filter-entity=<slug>]
```

**Default (no flags) → interactive loop.** For each item in the queue:

```
[3/12] research/claims/openai/gpt-5-energy-claim.md
  Title:    GPT-5 trained on 100% renewable energy
  Verdict:  mixed (analyst: mixed, auditor: false)  [needs_review]
  Status:   draft
  Sources:  4 cited, 4 ingested

[a]pprove  [s]kip  [p]review  [o]pen in editor  [q]uit  >
```

Single-key prompts via `click.prompt(..., type=click.Choice([...]))`. "Next" is implicit — pressing `a` or `s` advances. No back/prev in Phase 1.

**Actions:**
- `a` → call the new shared `approve_claim(claim_path, reviewer=None, notes=None, pr_url=None)` callable (see "Refactor" below). Reviewer is `None`, which falls through to `dr review`'s existing `git config user.email` lookup (`pipeline/orchestrator/cli.py:712-728`). No notes prompt in Phase 1 — `a` commits immediately. (`dr review` itself has no confirm prompt, so this is one-keystroke approve, which is the desired ergonomics for a queue.) On `ClickException`, print the message and re-prompt the same item rather than advancing.
- `s` → advance without changing state; the same item shows up next run
- `p` → `print(claim_path.read_text())` to stdout, paged through `less` if `len > $LINES`; loop re-prompts after preview
- `o` → `subprocess.Popen([editor, str(claim_path)])` where editor = `$VISUAL`, `$EDITOR`, falling back to `code`. Non-blocking (no `--wait`); operator returns to prompt manually
- `q` → exit cleanly

**Approve action — specifics resolved:**
- **Slug format passed in:** `<entity-slug>/<claim-slug>` (always — the queue knows the full path, no need for the bare-slug ambiguity branch)
- **Reviewer source:** delegate to the existing fallback in `dr review`. Don't re-implement it in the queue.
- **Confirmation prompts:** `dr review` has none — pressing `a` writes the sidecar and flips status in one step. Worth showing a one-line success echo from the queue ("Approved openai/foo-claim") so the operator has feedback before the next item paints.
- **Optional notes:** out of scope for `a` in Phase 1. Operator who wants to add notes drops out of the queue (`q`) and runs `dr review --notes "..." --approve --claim ...` manually. Re-evaluate if this becomes a frequent ask; could become Phase 2's `n` action that prompts for a one-line note then calls `approve_claim(notes=<input>)`.

**`--format text` flag:** prints a tab-separated table to stdout (slug, status, verdict, needs_review, path) and exits. Pipe-friendly.

**`--format json` flag:** prints a JSON array of queue entries and exits. CI-consumable. Schema:
```json
[
  {
    "claim_slug": "openai/gpt-5-energy-claim",
    "path": "research/claims/openai/gpt-5-energy-claim.md",
    "status": "draft",
    "verdict": "mixed",
    "auditor_verdict": "false",
    "needs_review": true,
    "sources_count": 4
  }
]
```

**`--filter-entity=<slug>`:** restricts the queue to one entity directory. Enough for Phase 1; broader filters land in Phase 2.

### Phase 2 — operator polish (only if Phase 1 is felt to be lacking)

- `c` set-criterion action. Background: `approve_claim` and the `published-without-criterion` lint now reject any draft -> published flip when `criteria_slug` is missing. Today's Phase 1 `a` action surfaces that error and re-prompts; the operator must drop out and either edit the claim frontmatter or the templates catalog by hand. A `c` action would prompt for an existing slug (or "create new" -> drop into `$EDITOR` on `research/templates.yaml`), write the chosen value into the claim frontmatter, then re-display so the operator can press `a`. See [`criterion-resolution-workflow_stub.md`](criterion-resolution-workflow_stub.md) for the full design space (manual edit, normalizer agent, singleton escape).
- `r` reject action with a concrete semantic. Proposed: write `human_review.notes` on the sidecar with operator-supplied text and leave `status: draft` — the item stays in the queue but carries a visible note for next pass. (Resists the urge to introduce a new status value.)
- `b` back / prev (requires keeping a history list)
- `e` quick edit-frontmatter-only mode (open file at the line of a specific field)
- `--filter-topic=<slug>`, `--filter-entity-type=<type>`
- Count and ETA in the prompt header
- Color (Click's `style()`)

### Phase 3 — pluggable queue types

Introduce a `Queue` protocol so the command becomes `dr review-queue --type=<name>`. Built-in types:
- `publication` (Phase 1's hardcoded behavior, refactored behind the protocol)
- `disagreement` (claims where `audit.needs_review` is true even after publication)
- `stale` (claims whose `next_recheck_due` is past)

Each type defines: `items(repo_root) -> list[QueueItem]`, `display(item) -> str`, `actions() -> dict[str, Action]`. The interactive loop becomes generic.

Defer until there's a second concrete queue type to design against.

## Refactor: extract `approve_claim` callable

The current `dr review` Click handler (`pipeline/orchestrator/cli.py:589-762`) is a 175-line monolith that does slug resolution, status pre-flight, reviewer resolution, sidecar write, status flip, and output in one block. Phase 1 needs to call the writing portion from a second site (the queue), and `subprocess.run([sys.argv[0], "review", ...])` is unreliable (`sys.argv[0]` may be `dr`, an absolute path, or `uv run dr` depending on context).

**Extraction:**
- New function `approve_claim(claim_path: Path, *, reviewer: str | None, notes: str | None, pr_url: str | None, mode: Literal["review", "approve", "archive"]) -> None` lives next to the Click handler in `cli.py` (or in a new `pipeline/orchestrator/review.py` if `cli.py` gets unwieldy)
- Takes a resolved `Path`, not a slug — slug resolution stays in the Click handler
- Encapsulates: status pre-flight, reviewer fallback (`git config user.email` lookup), sidecar load + mutate + write, `set_claim_status` flip
- Raises `ClickException` on validation errors; both call sites surface them the same way
- The existing `dr review` Click handler becomes a thin wrapper: parse + resolve + delegate
- The new `dr review-queue` interactive `a` action calls `approve_claim` directly with `mode="approve"`, reviewer/notes/pr_url all `None`

This refactor is in the critical path for Phase 1 — without it the `a` action has no clean implementation.

## Files to create / modify

| File | Change |
|------|--------|
| `pipeline/common/sidecar.py` | **NEW.** Promote `_read_sidecar` from `linter/runner.py:38-45` to a public `read_sidecar(claim_path: Path) -> dict \| None`. Add `sidecar_path_for(claim_path)` helper. |
| `pipeline/linter/runner.py` | Replace local `_read_sidecar` with import from `common.sidecar`. |
| `pipeline/orchestrator/cli.py` | **Refactor `review`** to extract `approve_claim` callable per above. Keep public CLI behavior identical. **Add new command** `review_queue`. |
| `pipeline/orchestrator/review_queue.py` | **NEW.** Queue-discovery logic: `find_publication_queue(repo_root) -> list[QueueItem]`. Pure function, easy to unit test. Also houses the interactive loop body so `cli.py` stays thin. |
| `pipeline/tests/orchestrator/test_review_queue.py` | **NEW.** Unit tests for `find_publication_queue` (fixtures: draft+sidecar+unreviewed → in queue; published → not in queue; draft without sidecar → not in queue; reviewed draft → not in queue; blocked → not in queue). `CliRunner` integration tests for `--format text`, `--format json`, and the interactive `a`/`s`/`p`/`q` keypaths driven via stdin. |
| `pipeline/tests/orchestrator/test_review.py` (or wherever `dr review` is tested) | Add a test asserting `approve_claim` and the existing `dr review --approve` produce byte-identical sidecar + claim file output. Guards the refactor. |
| `docs/UNSCHEDULED.md` or appropriate plan doc | Track Phase 2 / Phase 3 follow-ups so they don't get lost. |

## Reused existing code

- `pipeline/common/content_loader.py:48-78` `list_claims(repo_root, entity, topic)` — discovery
- `pipeline/orchestrator/cli.py:580-763` `dr review` — approval action (invoked as subprocess)
- Click prompts (`click.prompt`, `click.Choice`) — same pattern as `CLICheckpointHandler` (`pipeline/orchestrator/checkpoints.py:64-119`)
- `dr lint --format json` (`.github/workflows/ci.yml:37-43`) — JSON output convention

## Verification

End-to-end check after Phase 1 lands:

1. **Unit tests pass:** `inv test pipeline/tests/orchestrator/test_review_queue.py`
2. **Discovery is correct:** seed a temp repo with one of each (draft+sidecar+unreviewed, draft no sidecar, published, archived, reviewed draft, blocked); `find_publication_queue` returns exactly the first item.
3. **Refactor parity:** `test_review.py` asserts `approve_claim(...)` and `dr review --approve --claim ...` produce byte-identical sidecar YAML and claim frontmatter output on the same fixture.
4. **Interactive `a` is automated, not just manual:** `CliRunner` test pipes `"a\nq\n"` to `dr review-queue` against a one-item fixture queue and asserts (a) the sidecar `human_review.reviewed_at` was written, (b) the claim `status` flipped to `published`, (c) exit code is 0, (d) the queue then reports empty. Same shape for `s` (skip leaves state untouched) and `p` (preview emits the claim text to stdout without state change).
5. **Non-interactive output:**
   - `dr review-queue --format text` produces a tab-separated table with the right rows
   - `dr review-queue --format json | jq '.[].claim_slug'` returns the same set
   - Exit code is 0 whether the queue is empty or not (this is informational, not a CI-failing condition)
6. **Lint regression check:** before Phase 1 lands, `inv lint` passes; after Phase 1 lands and an item is approved through the queue, `dr lint` reports zero `published-without-review` issues for that claim.
7. **No coupling to in-pipeline checkpoints:** `inv test pipeline/tests/orchestrator/test_checkpoints.py` still passes unchanged.
8. **Manual smoke** (real repo): `dr review-queue` → press `o` (file opens in $EDITOR) → press `q` → file is unchanged.

## Open questions

These are non-blocking — Phase 1 can ship with the recommendations as written. Listed for visibility, not as gates.

1. **Reject semantics in Phase 2.** Proposal above is "write notes, leave draft." Alternative is a new `status: needs_revision` value, which expands the state machine. I lean toward the notes-only approach, but flagging now so the design isn't accidentally locked in by Phase 1 choices.
2. **VERSION pre-release exception.** The roadmap says published-without-review nulls are allowed during alpha/beta/rc. Phase 1 of `review-queue` doesn't depend on this — it surfaces unreviewed drafts regardless of release stage. The lint-check exception is a separate piece of work and out of scope for this plan.

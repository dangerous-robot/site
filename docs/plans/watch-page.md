# Watch page (SITE-AM) implementation plan

**Work item**: SITE-AM (Watch page), `docs/v1.0.0-roadmap.md`, beta.8, kind `minor`.
**Inputs**: `docs/plans/watch-page-ui-spec.md` (UI spec, moved there from `docs/plans/drafts/` in T0; owns markup, CSS, timings and test hooks, except where § 4 "Overrides to the UI spec" says otherwise), `docs/plans/drafts/watch-page-research-design.md`, `docs/plans/drafts/watch-page-research-architecture.md` (local-only background; every test and rule this plan needs is restated here).
**Drafted**: 2026-10-12 against the working tree at that date.

## Goal

Build a single `/watch` page with:
- a playlist list;
- a thumbnail grid for the selected playlist, with titles under the thumbnails;
- hover and focus popups;
- frame-cycling previews with an On/Off switch;
- a click-to-load `youtube-nocookie.com` viewer.

Data comes from YouTube Data API v3. It is fetched at build time by a custom Astro content loader, from a curated list in `src/content/watch/playlists.yaml`. No API data is committed. A weekly scheduled deploy keeps the data under the 30-day storage limit (YouTube API Services Developer Policies III.E.4). The page is not added to the nav.

## Status

- [x] T0: Review, promote the plan and UI spec, register the work item
- [x] T1: Dev dependency and npm scripts (wave 1)
- [x] T2: Types, schemas, timings and UI contract (wave 1)
- [x] T3: Curated playlists and fixture curated list (wave 1)
- [x] T4: Duration parsing and text (wave 2, lane A) [parallel]
- [x] T5: YouTube API client with pagination, batching, retry, redaction, error mapping (wave 2, lane A) [parallel]
- [x] T6: Normalize and filter, including the non-embeddable drop (wave 2, lane A) [parallel]
- [x] T7: Build orchestration, mode resolution, log lines, fixture fetch (wave 2, lane A) [parallel]
- [x] T8: Client pure logic: URL state, preview gate and cycler, frames, popup placement (wave 2, lane B) [parallel]
- [x] T9: Privacy page and Base.astro comment (wave 2, lane C) [parallel]
- [x] T10: Content collection and loader wiring (wave 3)
- [x] T11: Page shell, EmptyState slot, stub components, client main, Playwright scaffold (wave 3)
- [x] T12: Playlist tabs (wave 4, lane D) [parallel]
- [x] T13: Player, including autoplay only when half on screen (wave 4, lane E) [parallel]
- [x] T14: Panels, thumbnails, card clicks and popup (wave 4, lane F) [parallel]
- [x] T15: Preview switch and frame cycling (wave 4, lane G) [parallel]
- [x] T16: Post-build dist check script (wave 4, lane H) [parallel]
- [x] T22: Cross-lane browser tests after the wave 4 merge (wave 5)
- [x] T17: Wire checks into npm, Invoke and CI; weekly scheduled deploy of main (wave 5)
- [x] T18: Architecture docs and roadmap (wave 5)
- [x] T19: Live key verification on Brandon's machine (wave 6)
- [ ] T21: Manual-dispatch deploy verification of the per-playlist fetch log lines (wave 6, ask Brandon first)
- [ ] T20: Manual browser check and first deploy (wave 6, ask Brandon first)

## Redesign (two-column switcher layout)

Source: Design canvas artboard `project/WatchSwitcher.dc.html` (https://claude.ai/code/artifact/f999538d-53b8-48f2-bd7c-b26a49c04269). It replaces the tabs, thumbnail grid, popups and frame previews. Brandon's decisions, 2026-10-12:

| ID | Decision |
|----|----------|
| RD1 | Desktop: one viewport tall (600px minimum, then the page scrolls). Standard nav, then a resizable list column (380px, 300 to 560px by drag or arrow keys) beside the player column, then a one-line footer. At 860px and below the columns stack, player first. |
| RD2 | Playlist switcher at the top of the list column: "Playlist  N of M", the current playlist's card as a disclosure button, a menu of the other playlists over a scrim (Escape or scrim click closes it), and an always-present one-line status ("Now playing: <title>" or "Back to now playing in <playlist>"). Each playlist keeps its own list scroll position. |
| RD3 | Rows: 128px thumbnail with duration, two-line title, channel and date. The video in the player (poster or playing) is current from first load: accent bar, highlighted background and a Playing badge over the thumbnail. No indicator changes layout. |
| RD4 | Hover popups, frame previews and the preview switch are removed. No autoplay of the next video. |
| RD5 | /watch stays out of the nav. Visually hidden h1 "Watch"; the video title stays an h2; no breadcrumb or visible intro. |
| RD6 | The YouTube attribution line under the player is removed. The YouTube Terms link lives on /privacy (D9), and the dist check requires it there. |
| RD7 | Scrollbars site-wide: `color-scheme` per theme; page scrollbars keep their normal width with theme colours; lists and menus get thin scrollbars whose thumb always shows. Thumbs are 3:1 against the page background. |
| RD8 | `?list=&v=` deep links stay as built; extending them is undecided. |

- [x] RD-T1: Base `app` layout, tokens (menu, scrim, scrollbar in all four themes), scrollbar rules
- [x] RD-T2: Switcher, list, player and resizer markup and client; popup and preview code removed
- [x] RD-T3: Dist check: menu options replace tabs; Terms link checked on /privacy
- [x] RD-T4: Unit tests for width limits and the now-playing line
- [x] RD-T5: Browser tests rewritten for the new layout
- [x] RD-T6: Browser check at 1280x800, 600px tall, 860px wide and phone width, in dark, light and high contrast; /simplify and review

## Decisions (final, from Brandon, 2026-10-12)

| ID | Decision |
|----|----------|
| D1 | Route `/watch`, one page: playlist switcher, video list, embedded viewer, laid out per § Redesign. No hover popups. |
| D2 | Build-time fetch in CI through a custom content loader. The curated list `src/content/watch/playlists.yaml` holds playlist ID, slug, editor description and order. No committed API snapshot. |
| D3 | Key is in env var `YOUTUBE_API_KEY`, set as a GitHub repository secret. If there is no key, the page renders the empty state. Tests use fixture data. |
| D4 | If the API fails during a deploy build, publish the empty state and keep the deploy green. Log a clear warning. There is no failing `required` mode, which overrides the architecture research's DEC-3. |
| D5 | Weekly scheduled deploy (cron) in `.github/workflows/deploy.yml`. A scheduled run rebuilds the default branch exactly like a push deploy, `verify` included. Every push to main already deploys, so production is `origin/main` HEAD and a scheduled run ships only refreshed YouTube data. |
| D6 | Images come from `i.ytimg.com`. There are no hover frame previews (§ Redesign); the loader still records a frame tier, which nothing reads. |
| D7 | Player: click-to-load `youtube-nocookie.com/embed/<id>` iframe. No IFrame API, no play-next. Autoplay waits until the player box is at least half on screen (UI spec § 4.7). |
| D8 | No preview switch: hover previews are removed (§ Redesign). |
| D9 | The privacy page gets a `/watch` exception and links YouTube Terms of Service and the Google Privacy Policy where policy requires (Developer Policies III.A.1, III.A.2). |
| D10 | Playwright browser tests (new dev dependency) and node:test unit tests use fixtures. There is no network in tests. |
| D11 | Seed order: `PLXFc9I7KsRUk` ("Dangerous Robot"), FAR.AI "AI Safety - Research Highlights" `PLpvkFqYJXcreU5HqW6aUYeppYPG8aBRZ_`, Oxford Institute for Ethics in AI "Colloquia and Lectures" `PLf4lTwFHevBuvTDX4m8N5WVAX62IkhXJ7`. |
| D12 | Not in nav. The intro is the meta description only; the page shows a visually hidden h1. |
| D13 | All three seed playlists are public and readable with the API key (Brandon checked: `PLXFc9I7KsRUk` 4 videos, FAR.AI 63, Oxford 53). There is no editor fallback list. A playlist the API cannot read produces a per-playlist warning and is shown as failed, or omitted when even its title is unknown (§ 2). |
| D14 | `YOUTUBE_API_KEY` is a GitHub Actions repository secret. The key carries an API restriction (YouTube Data API v3) and no HTTP referrer restriction, and it works from Brandon's machine. The loader never sets or spoofs a `Referer` or `Origin` header to get around a key restriction. |
| D15 | Remote actions (git push, PRs, `workflow_dispatch`, deploys) are Brandon's call. There is no PR workflow before beta: work lands on local main, checks run locally, and CI runs after Brandon pushes. |

Decisions this plan makes (reviewer to check):

| ID | Decision | Why |
|----|----------|-----|
| P1 | Fixtures are synthetic: real response shape, invented IDs and text. | A committed recording of real responses is API data kept past 30 days, the same problem as a snapshot. |
| P2 | One collection, `watchPlaylists`. Each entry is a normalized playlist with its videos embedded. The loader reads the YAML itself with `js-yaml`, as `criteria` does in `src/content.config.ts:262`. | Avoids the unverified cross-collection store read and keeps one source of truth for the page. |
| P3 | `?list=` is the curated `slug` from the YAML; `?v=` is the YouTube video ID. URL changes use `history.replaceState`. | UI spec CF-6: short, readable, stable if a playlist ID is swapped. |
| P4 | Non-embeddable videos (`status.embeddable` false) are dropped at build, counted in the log line. | UI spec CF-7: one fewer player state, and the count shows what is on the page. |
| P5 | Playwright runs on Chromium only, as an `e2e` job in `ci.yml`. It runs wherever `ci.yml` runs (pull requests, and push deploys through `verify`). It is not part of the pre-commit hook. Scheduled deploys run it too (P7). | Browser binaries do not belong in every local commit. |
| P6 | Loader modes: `fixture` when `WATCH_DATA=fixture`, `live` when a key is present, `none` otherwise. Global API failures fall back to `none` with a warning. | D3 and D4. |
| P7 | A scheduled run uses the same jobs as a push deploy (`verify`, `build`, `deploy`), with no `if:` conditions, no ref change and no extra checkout options. `check:watch` runs as a plain `npm run check:watch`. | A `schedule` event checks out the default branch's latest commit, which push deploys have already shipped (D5). |
| P8 | In `none` mode the page renders one page-level empty state (`watch-page-empty`) and no tabs, player, switch or panels. Per-panel failed states (UI spec § 5) appear only in `live` or `fixture` mode for a playlist whose title is known. | Without API data there is no playlist name to put on a tab. |
| P9 | Client code is split into one controller file per component under `src/components/watch/client/`, instead of the UI spec's single `watch-client.ts`. | Wave 4 lanes need disjoint files. |

## 1. Repo facts this plan rests on

| Fact | Where |
|------|-------|
| Unit tests: `npm run test:site` = `tsx --test 'src/lib/**/*.test.ts'` (node:test, `node:assert/strict`). | `package.json`, `src/lib/httpUrl.test.ts` |
| `npm run check` = check:types, test:site, build, lint:md, check:citations, check:reviewers. | `package.json` |
| `inv check` = `npm run check:types`, `npm run test:site`, `npm run build`, `lint:md`, `check:citations`, pipeline pytest. It does not run `check:reviewers`. | `tasks.py:39-46` |
| Pre-commit runs `dr lint`, then `inv check` (a full site build). It exits 0 and skips everything when `pipeline/.venv/bin/dr` is missing, so commits from a fresh worktree are not verified by the hook. Untracked research output in the main checkout can fail the build and block every commit there. | `.git/hooks/pre-commit` |
| `ci.yml` triggers on `pull_request` and `workflow_call`. Its `check` job runs test:site, build, lint:md and check:citations; it does not run check:types. | `.github/workflows/ci.yml` |
| `deploy.yml` triggers on push to `main` and `workflow_dispatch`, with no schedule, so every push to main deploys and production is `origin/main` HEAD. `verify` calls `ci.yml` (jobs `check` and `lint-content`, which runs `dr lint`); `build` needs `verify`; `deploy` needs `build`. The `build` job declares no `environment`, so an environment-scoped secret would be invisible to it. | `.github/workflows/deploy.yml`, `.github/workflows/ci.yml` |
| `docs/plans/drafts/` is gitignored, so worktrees and CI never see drafts. | `.gitignore:24` |
| Local `main` is 178 commits ahead of `origin/main` (2026-10-12). | `git rev-list --count origin/main..main` |
| Harness-made worktrees branch from origin. The gate hook resolves edit paths against `$CLAUDE_PROJECT_DIR` (the main checkout), so an edit under a sibling `../site-wt-*` worktree is outside its root and not gated; the main checkout's record (T0) is the one that counts. Subagent Bash calls reset their cwd to the main checkout. | `scripts/release-gate/release_common.py:76-99`, `.claude/settings.json`, coordinator instructions |
| Zod for testable schemas comes from `astro/zod` outside `content.config.ts`. | `src/lib/matrixSchema.ts:5` |
| Data passes to scripts as `<script type="application/json">` built with `jsonForScript`. | `src/lib/jsonForScript.ts:12` |
| Build-time fetch with graceful fallback already exists. | `src/lib/petition.ts` (`fetchPetitionState`) |
| `formatPostDate` is pure, but `src/lib/writing.ts` imports `astro:content`, so it can be used only in `.astro` files at build time. | `src/lib/writing.ts:1`, `:21` |
| Storage keys use the `dr-` prefix and try/catch wrappers. The Motion setting is `dr-motion`, mirrored to `html[data-motion]`. | `src/components/A11yControl.astro:322-343`, `src/layouts/Base.astro:130` |
| Base layouts are `reading`, `wide` and `bare`. | `src/layouts/Base.astro:28-29` |
| `Base.astro:2` comment says pages make no third-party requests. `privacy.astro:19` says "The site runs no analytics or tracking scripts." | as cited |
| `EmptyState` takes only a `message` prop and has no slot. Its seven users: `src/pages/research/{subjects,products,sources,criteria,claims,companies}/index.astro` and `src/pages/research/topics/[topic].astro`. | `src/components/EmptyState.astro` |
| `trailingSlash: "never"`. The sitemap integration includes all pages by default. | `astro.config.ts` |
| Release gate covers `src/` (except `src/content/`), `scripts/`, `public/`, `.github/`, `package.json`, `package-lock.json`, `tasks.py`, `tsconfig.json`, `astro.config.ts`. `docs/`, `src/content/`, `.claude/` and `*.md` are exempt; `tests/` and `playwright.config.ts` are not gated. No work item is active now. | `scripts/release-gate/release_common.py:24-54`, `work_item.py status` |
| Node 22 (engines `>=22`, local v22.22.3). | `package.json` |
| `.env` is gitignored. `.env.example` is the pipeline's sample and has no YouTube entry. | `.gitignore`, `.env.example` |
| The `YOUTUBE_API_KEY` repository secret exists and is API-restricted only (D14). | Brandon, 2026-10-12 |
| The operator keeps `inv dev` running on port 4321. | operator convention |

Unverified, checked in a task:
- Whether `process.env` sees root `.env` values inside `content.config.ts` during `astro build`. Checked in T10.
- Whether a `::warning` line printed with `console.log` from inside the loader reaches the CI log at the start of a line (Astro's logger would prefix it). Checked in T10 locally and in T21 in the run's Annotations list.
- Whether the 404 placeholder image fires `onerror`. Checked in T15; detection also uses `naturalWidth`.
- Whether Astro scopes or hoists a `<style>` inside `<noscript>`. T11 uses `is:inline`; the no-JS browser test confirms.

## 2. Architecture

```
src/content/watch/playlists.yaml        curated list (editorial, ungated)
        |
src/content.config.ts  watchPlaylists = custom loader 'watch-youtube'
        |   reads YAML, resolveMode(env), loadWatchData({curated, client, log})
        v
src/lib/watch/*.ts (pure, unit tested)  youtube.ts -> normalize.ts -> load.ts
        |
src/pages/watch.astro  getCollection('watchPlaylists') sorted by order,
        |   adds publishedText (formatPostDate), server-renders tabs, player
        |   poster, panels (non-selected hidden), <script type="application/json" data-watch-data>
        v
src/components/watch/client/main.ts     state + URL + bus; one controller per component
```

Modes (P6), all resolved in `src/lib/watch/env.ts`:

| Mode | When | Result |
|------|------|--------|
| `fixture` | `WATCH_DATA=fixture` | `src/lib/watch/fixtures/playlists.fixture.yaml` is served by `fixtureFetch` from `src/lib/watch/fixtures/api/*.json`. Same code path as live. |
| `live` | `YOUTUBE_API_KEY` set | Real API calls. Per-playlist errors produce warnings. Global errors (quota, key rejected, network after retries, malformed JSON) produce `none` plus a warning. |
| `none` | Neither set | No entries. The page renders the page-level empty state (P8). If `WATCH_EXPECT_KEY=1` (deploy), a warning says the key is missing. |

Requests carry only `key`, `part`, `fields`, `id`/`playlistId`, `maxResults` and `pageToken` query parameters. No `Referer`, `Origin` or custom headers are set. A referrer-restricted key is a configuration error to fix in Google Cloud, not in code.

Per-playlist outcomes in `live` and `fixture` mode:

| Case | Behaviour |
|------|-----------|
| `playlists.list` returns the ID and `playlistItems.list` works, at least one video kept | `status: ok`. `fetched` line. |
| Readable, but every video is filtered out | `status: empty`. Panel: "This playlist has no public videos right now." `fetched` line with `0 videos`. |
| Title known from `playlists.list`, but `playlistItems.list` fails for any reason other than a key or quota error (for example 404, 403 not about the key, 400, 5xx after retries, timeout) | `status: failed`, no videos. Panel: "These videos could not be loaded." plus "See the playlist on YouTube". Warning. |
| The ID is missing from the batched `playlists.list` response | Omitted from the page. Warning plus `skipped` line. |

Global errors stop the load. A key error is any response whose `error.errors[0].reason` is `keyInvalid` (whatever the status, since an invalid key can return 400), or a 403 `forbidden` whose `error.message` mentions `referer` (case-insensitive). Quota (`quotaExceeded`), network after retries and malformed JSON are also global.

**Log lines.** Warnings go to `console.warn` with the prefix `[watch loader]`. When `GITHUB_ACTIONS=true`, each warning is also printed with `console.log` (stdout) as `::warning title=Watch page::<text>`, at the start of the line. `<text>` escapes `%`, CR and LF as `%25`, `%0D` and `%0A` (GitHub workflow-command encoding), so API text can never end the annotation early or start another workflow command.

Every warning caused by an API error includes:
- the call (`playlists.list`, `playlistItems.list` or `videos.list`);
- the playlist ID, where there is one;
- the HTTP status;
- the API's `error.errors[0].reason` (for example `forbidden`, `quotaExceeded`, `keyInvalid`, `playlistNotFound`);
- the API's `error.message`, verbatim (for example `Requests from referer <empty> are blocked.`).

Example: `[watch loader] warning: playlists.list failed (403 forbidden): Requests from referer <empty> are blocked. Rendering the empty state.`

Key text is never printed. The client redacts the key from the message and from any URL before logging (U6). The API does not echo the key in these messages, but redaction runs anyway.

Info lines, in this fixed format (U21 and T21 grep for them):
- one per kept playlist: `[watch loader] fetched <playlistId>: <n> videos (dropped: <k>, not embeddable: <e>)`, where `<k>` is the total dropped for any reason and `<e>` is the part of it that was not embeddable;
- one per omitted playlist: `[watch loader] skipped <playlistId>: <reason>`;
- on a global error, after its single warning: one `skipped <playlistId>: global API error (<reason>)` line per curated playlist;
- always last: `[watch loader] mode=<live|fixture|none> playlists=<n> videos=<total>`.

**Filtering** (architecture research § 2): a video is kept only if `videos.list` returned it, `privacyStatus` is `public` or `unlisted`, `uploadStatus` is `processed`, `liveBroadcastContent` is `none` and `embeddable` is true. Duplicates are de-duplicated by first `position`. Order follows `position`. `max_videos` caps each playlist (default 50; FAR.AI and Oxford are capped). `videos.list` requests `part=snippet,contentDetails,status`.

**Frame tier**: `sd` if the API returned `thumbnails.standard`, else `mq`. The client also skips a frame that errors or loads with `naturalWidth <= 120` (the 404 placeholder).

## 3. Curated YAML schema

`src/content/watch/playlists.yaml`:

```yaml
playlists:
  - slug: dangerous-robot             # ^[a-z0-9]+(-[a-z0-9]+)*$, unique; used in ?list=
    playlist_id: PLXFc9I7KsRUk        # ^PL[A-Za-z0-9_-]{11,32}$, unique
    order: 1                          # unique positive int
    description: "<editor copy, max 200 chars>"
    creator: "<optional override of the owner channel name>"
    max_videos: 50                    # optional, 1..200, default 50
```

The schema rejects:
- duplicate `slug`, `playlist_id` or `order`;
- a slug that is not kebab-case;
- a bad playlist ID shape;
- a description over 200 characters;
- unknown keys (strict object), so a stray field is caught.

## 4. Shared contracts (frozen in wave 1, T2)

Everything below lives in `src/lib/watch/types.ts`, `src/lib/watch/contract.ts` and `src/lib/watch/timings.ts`. Values are final: they come from the UI spec. Wave 3 and 4 code imports them and must not redefine them.

**Types (`types.ts`)**

```ts
export type WatchMode = 'live' | 'fixture' | 'none';
export type FrameTier = 'sd' | 'mq';
export type PlaylistStatus = 'ok' | 'empty' | 'failed';
export interface WatchCover { src: string; srcset: string }
export interface WatchVideo {
  id: string; title: string; channel: string;
  durationText: string; durationSpoken: string;   // both '' when unparseable
  publishedIso: string;
  description: string;                            // plain text, max 500 chars plus ellipsis
  cover: WatchCover; frameTier: FrameTier;
}
export interface WatchPlaylist {
  slug: string; youtubeId: string; order: number;
  name: string; creator?: string;                 // YAML creator, else API channelTitle
  description: string;                            // YAML, else API description cut at a word to 200
  status: PlaylistStatus; dataMode: Exclude<WatchMode, 'none'>;
  videos: WatchVideo[];
}
// The page adds publishedText at build (formatPostDate); these are the UI spec's view model.
export type WatchVideoView = WatchVideo & { publishedText: string };
export type WatchPlaylistView = Omit<WatchPlaylist, 'videos'> & { videos: WatchVideoView[] };
export interface WatchBuildResult { mode: WatchMode; playlists: WatchPlaylist[]; warnings: string[] }
export interface WatchState {
  selectedSlug: string;                           // tab shown
  video: { slug: string; id: string } | null;     // in the player
  loaded: boolean;                                // a known deep-linked v, or an embed that has started (watch:play)
  notice: boolean;                                // unknown v on arrival
}
```

The client JSON block is `<script type="application/json" data-watch-data>` holding `{ playlists: WatchPlaylistView[] }`, serialized with `jsonForScript`.

**Constants (`contract.ts`)**

| Contract | Value |
|----------|-------|
| `TESTID` map | UI spec § 8: `watch-page`, `watch-lede`, `watch-tablist`, `watch-tab`, `watch-panel`, `watch-panel-count`, `watch-grid`, `watch-thumb`, `watch-thumb-title`, `watch-thumb-duration`, `watch-popup`, `watch-player`, `watch-player-frame`, `watch-play`, `watch-iframe`, `watch-player-title`, `watch-player-meta`, `watch-youtube-link`, `watch-back-link`, `watch-notice`, `watch-preview-switch`, `watch-preview-hint`, `watch-status`, `watch-empty` (per-panel empty or failed). Plus `watch-page-empty` (page-level empty state in `none` mode, P8). |
| Data attributes | `data-watch-mode` on the `watch-page` root; `data-playlist="<slug>"` on tab, panel, thumb and player; `data-video-id` on thumb, player and popup; `data-frame-tier` (`sd` or `mq`) on each thumb; `data-previewing="true"` and `data-frame="1|2|3"` on a cycling thumb; `data-value="on|off"` on switch radios; `data-watch-data` on the JSON block. |
| CSS classes | UI spec § 7.2, prefix `watch-`, BEM-style elements (`.watch-thumb__media`). Scoped `<style>` in each component; nothing added to `src/styles/global.css`. Page-level blocks (`.watch`, `.watch-layout`, `.watch-rail`, `.watch-main`, `.watch-toolbar`, `.watch-attribution`, `.lede`) live in `watch.astro`. Classes on elements that JS creates (`.watch-thumb__frame`, `.is-shown`, `.watch-player__iframe`) must be styled with `:global()` inside their owner's scoped block, because Astro scoping does not reach inserted nodes. `CLASS` in `contract.ts` exports the names JS touches: `thumbMedia`, `thumbFrame`, `frameShown`, `thumbPlaying`, `playerIframe`. |
| Storage key | `dr-watch-previews`, values `on` or `off`, written only on an explicit choice. |
| Bus events | `WATCH_EVENTS = { playlist: 'watch:playlist', video: 'watch:video', play: 'watch:play', preview: 'watch:preview' }` on one `EventTarget` created in `client/main.ts`. Details in `types.ts`: playlist `{slug}`, video `{slug, id, play: boolean, notice: boolean}`, play `{slug, id}`, preview `{enabled}`. `play: false` means "show this poster"; only `play: true` and `watch:play` mark a card playing. |
| Startup and ownership | `main.ts` parses the URL, calls every `init*`, then emits `watch:playlist` for the arrival tab and `watch:video {play: false}` for the arrival poster (with `notice: true` for an unknown `v`). It does not announce at startup. `main.ts` owns `WatchState`: a known deep-linked `v` and `watch:play` set `loaded`, so `?v=` names a video only once its embed has started (a pick still waiting for the player to scroll into view does not change the URL); on a reader's tab change while `loaded` is false and no pick is waiting, it emits `watch:video {play: false}` for the new playlist's first video (UI spec § 4.6), and emits nothing for a playlist with no videos (§ 5). Controllers render what the bus says and keep no copy of the selection state. |
| Embed | `https://www.youtube-nocookie.com/embed/<id>?autoplay=1&rel=0`, `allow="autoplay; encrypted-media; picture-in-picture; fullscreen"`, `allowfullscreen`, `title="<title> (YouTube video)"`. Never a `referrerpolicy` attribute on the iframe. |
| Autoplay gate | `PLAYER_MIN_VISIBLE_RATIO = 0.5`: an iframe is inserted only when the player frame is at least half in view (UI spec § 4.7). |
| Breakpoints | `BREAKPOINT_DESKTOP_PX = 1120` (rail beside the main column at 1120px and up), `BREAKPOINT_PHONE_PX = 640` (one grid column at 640px and down). CSS uses the same literal values (UI spec § 2). |
| Controller signature | Each `src/components/watch/client/<name>.ts` exports `init<Name>(root: HTMLElement, bus: EventTarget, data: WatchPlaylistView[]): void`. |
| Component props | UI spec § 3.3: `WatchPlaylistTabs {playlists, selectedSlug}`, `WatchPlayer {video: WatchVideoView \| null, playlist: WatchPlaylistView \| null}`, `WatchPanel {playlist, selected, eagerFirstRow}`, `VideoThumb {video, playlist, eager}`, `VideoPopup {}`, `PreviewSwitch {}`. |

**Timings (`timings.ts`, UI spec § 4.1)**

`POPUP_OPEN_DELAY_MS 300`, `POPUP_CLOSE_DELAY_MS 150`, `POPUP_FADE_MS 150`, `FRAME_LOAD_AT_MS 300`, `FRAME_FIRST_AT_MS 600`, `FRAME_INTERVAL_MS 900`, `FRAME_FADE_MS 200` (0 under a reduce setting).

**Layout**: `<Base title="Watch" layout="wide">`; breakpoints and grid per UI spec § 2 and § 7.2 (desktop 1120px and up: sticky `15rem` rail plus 2 grid columns; tablet 641 to 1119px: stacked rail, 2 columns; phone 640px and down: stacked rail, 1 column).

**Overrides to the UI spec.** Where the promoted UI spec says otherwise, this list wins:

| Spec text | This plan |
|-----------|-----------|
| § 3.1: `src/components/watch/watch-client.ts` | `src/components/watch/client/{main,tabs,player,grid,popup,preview}.ts` (P9). The page script imports `client/main.ts`. |
| § 3.3 page outline | Adds `data-watch-mode` to the `watch-page` root. In `none` mode the page renders only the page-level empty state (P8). |
| § 4.6 and § 4.8: arrival and poster-follow rules, no owner named | `main.ts` applies them through the bus (§ 4 "Startup and ownership"). |
| § 3.2: view model built in the page | The loader stores `WatchPlaylist`; the page adds only `publishedText` (§ 4 types). |

## 5. Tests

Unit tests (node:test, `src/lib/watch/**/*.test.ts`, no network):

| ID | What it checks | Task |
|----|----------------|------|
| U1 | `parseIsoDuration` (`PT22M58S`, hours, zero, junk gives `null`); `formatDuration` (`m:ss`, `h:mm:ss`); `spokenDuration` ("22 minutes 58 seconds", singulars) | T4 |
| U2 | `listPlaylistItems` follows `nextPageToken` and stops at `max` | T5 |
| U3 | `listPlaylists` makes one batched call; `listVideos` batches by 50 | T5 |
| U4 | Normalize: keep rules (§ 2), de-dup by first position, order, `max_videos`, dropped counts by reason, frame tier `sd` only with `standard`, cover `srcset` sorted by width, description cuts (500 video, 200 playlist at a word) | T6 |
| U5 | A 403 `quotaExceeded` is global: `mode: 'none'` plus a warning, nothing throws | T5, T7 |
| U6 | Redaction: a key with a distinctive marker never appears in error messages, URLs or warnings. The test key does not start with `AIza`, so the lane's leak grep stays clean | T5 |
| U7 | Curated schema rejects each § 3 case; the `WatchPlaylist` schema accepts normalized output | T2 |
| U8 | `parseUrl` and `toSearch` round trip, plus every arrival rule in UI spec § 4.8 (known and unknown `list` and `v`, `v` without `list`, URL after a video is loaded). A known deep-linked `v` arrives with `loaded: true`, so the URL keeps it; an unknown `v` arrives with `loaded: false` and `notice: true` | T8 |
| U9 | `previewsEnabled(stored, osReduce, siteReduce)` truth table (UI spec § 4.5) | T8 |
| U10 | Cycler with a fake clock and image loader: nothing requested before `FRAME_LOAD_AT_MS`, first frame at `FRAME_FIRST_AT_MS`, advances every `FRAME_INTERVAL_MS`, skips failed frames, stops and restores | T8 |
| U11 | `frameUrls(id, tier)`, `coverSrcset(cover)`, `isPlaceholder(naturalWidth)` | T8 |
| U12 | An ID missing from `playlists.list` is omitted, with a warning and a `skipped` line | T7 |
| U13 | `playlistItems.list` 404 and 403 (not key errors) give `status: failed` with a warning | T7 |
| U15 | `resolveMode(env)` for each mode; `WATCH_DATA=fixture` wins over a present key (fixture builds and e2e must stay offline once the key is in `.env`); the missing-key warning when `WATCH_EXPECT_KEY=1` | T7 |
| U16 | `placePopup`: right, then left, then below; never above; 16px horizontal clamp; top clamped below the player bottom; `null` when it would still intersect the player | T8 |
| U17 | Both YAML files parse and validate against the curated schema | T3 |
| U18 | The fake `fetch` records its `init`: no call passes `headers`, and no `referer` or `origin` header (case-insensitive) is ever set | T5 |
| U19 | The 403 referer-blocked body and a 400 `keyInvalid` body each give `kind: 'key'`, `scope: 'global'`; the formatted warning has the reason and the verbatim message | T5 |
| U20 | A global key rejection gives `mode: 'none'`, exactly one warning (reason and message, no key text), one `skipped ... global API error` line per curated playlist, and `mode=none playlists=0 videos=0`; with `GITHUB_ACTIONS=true` the `::warning title=Watch page::` line is logged, and an API message containing a newline and `%` comes out as one line with `%0A` and `%25` | T7 |
| U21 | A fixture load logs `fetched` lines for Alpha (n > 0) and Bravo (0 videos), a warning for Charlie, a `skipped` line for Delta, and `mode=fixture playlists=3 videos=<n>` | T7 |
| U22 | A non-embeddable video is dropped and counted in `not embeddable` | T6 |

Browser tests (Playwright, Chromium, fixture build):

| ID | What it checks | Task |
|----|----------------|------|
| E1 | Selecting a tab swaps the panel and sets `?list=<slug>` | T12 |
| E2 | `?list=<slug>&v=<id>` shows that poster and no iframe | T13 |
| E3 | Hover cycles the frame layer through 1, 2, 3 (`data-frame`), leaving restores the cover | T15 |
| E4 | Off stops cycling and persists across reload (`dr-watch-previews=off`) | T15 |
| E5 | `reducedMotion: 'reduce'` defaults to Off with the hint; explicit On then cycles; `dr-motion=reduce` behaves the same | T15 |
| E6 | Keyboard: tab arrows, Home, End, manual activation with Enter or Space; switch radios by arrow keys | T12, T15 |
| E7 | No request to `youtube-nocookie.com` before Play | T13 |
| E8 | The popup never intersects the `watch-player-frame` box: on first-row cards in T14, and again with an iframe in the player in T22 | T14, T22 |
| E9 | The player frame is at least 200x200 at a 320px viewport | T13 |
| E10 | Autoplay gate: with `Element.prototype.scrollIntoView` stubbed to a no-op (`addInitScript`), clicking a card far down the grid inserts no `watch-iframe`; scrolling the player to at least half in view then inserts exactly one | T22 |
| E11 | Poster follows the selected tab until a video is loaded, then stays (UI spec § 4.6); a deep-linked `v` keeps its poster on tab change. T13 covers arrival by deep link (`?list=`, `?v=`); the tab-click half needs `tabs.ts` and runs in T22 | T13, T22 |
| E12 | Show more appears only for an overflowing description and toggles `aria-expanded` and its label; Back to video list focuses the first card of the selected panel when nothing is playing (the playing-card case is in T22) | T13 |

E2E specs run against the T11 stubs for other lanes' components, so a lane tests only what its own controller does with bus events. Flows that cross two wave 4 lanes (card click through `grid.ts` into `player.ts`) are tested after the merge, in T22.

The UI spec § 8 four-theme screenshots are a manual check (§ 8 manual list), not an automated test.

## 6. Tasks

Each task lists its files, what to build, how to verify it, and a commit message. "Verify" always includes `npm run check:types`, `npm run test:site` and `npm run build`. Lanes in worktrees run these themselves before every commit (§ 7). In the main checkout, stage explicit paths only (`git add <paths>`): a peer session shares it.

### T0: Review, promote the plan and UI spec, register the work item (orchestrator, main checkout)

- Files: `docs/plans/watch-page.md`, `docs/plans/watch-page-ui-spec.md`, `docs/v1.0.0-roadmap.md` (SITE-AM plan links; tick "Research" and "Implementation plan").
- Do:
  1. A reviewer appends a row to `## Review history` and a row with Type `reviewed` to `## Edit history`. implement-plan only recognises the second.
  2. Move (not copy) both drafts to `docs/plans/` (drafts are gitignored, and lanes work from committed files). Add a `## Review history` table to the UI spec (AGENTS.md § Plan review records) and a line under its title: "Where this spec and `watch-page.md` § 4 'Overrides to the UI spec' differ, the plan wins."
  3. Run `git diff docs/v1.0.0-roadmap.md` first. If it shows changes this plan did not make, ask Brandon before staging that file.
  4. Run `python3 scripts/release-gate/work_item.py start --title "SITE-AM (Watch page)" --kind minor --release v1.0.0 --plan docs/plans/watch-page.md`.
  5. Open the handoff note `handoff/2026-10-12-watch-page.md` (or update it if it exists). Only the orchestrator writes it.
- Verify: `python3 scripts/release-gate/work_item.py status` shows `Gate verdict: ALLOW`. `git ls-files docs/plans/watch-page.md docs/plans/watch-page-ui-spec.md` lists both after the commit.
- Commit (explicit paths): `docs(plans): promote watch page plan and UI spec (SITE-AM)`

### Wave 1 (serial, main checkout)

#### T1: Dev dependency and npm scripts

- Files: `package.json`, `package-lock.json`.
- Do:
  - `npm install -D @playwright/test`.
  - Add scripts `"test:e2e": "playwright test"` and `"check:watch": "tsx scripts/check-watch-page.ts"`. They are not yet in `check`; T17 adds `check:watch`.
  - All `package.json` edits in this plan happen here and in T17 only.
- Verify: `npx playwright --version` prints a version; `npx playwright install chromium` succeeds.
- Commit: `chore(watch): add Playwright and watch page npm scripts`

#### T2: Types, schemas, timings and UI contract

- Files: `src/lib/watch/types.ts`, `src/lib/watch/contract.ts`, `src/lib/watch/timings.ts`, `src/lib/watch/schema.ts`, `src/lib/watch/schema.test.ts`.
- Do:
  - Write the § 4 contracts with their final values.
  - Write the Zod schemas (from `astro/zod`) for the curated YAML (§ 3) and for `WatchPlaylist`.
  - Write U7.
- Verify: `npm run test:site` includes `schema.test.ts` and passes. `npm run check:types` reports 0 errors.
- Commit: `feat(watch): add watch data types, schemas, timings and UI contract`

#### T3: Curated playlists and fixture curated list

- Files: `src/content/watch/playlists.yaml`, `src/lib/watch/fixtures/playlists.fixture.yaml`, `src/lib/watch/playlists.test.ts`, `.env.example`.
- Do:
  - Seed the three playlists in D11 order with slugs `dangerous-robot`, `far-ai-research-highlights` and `oxford-ethics-colloquia` (Brandon can rename them before the first deploy; Q1), and stub editor descriptions marked in a YAML comment for Brandon to rewrite.
  - The fixture list has four synthetic playlists (IDs pass the regex):
    - `alpha` / `PLfixtureAlpha01`: readable, two `playlistItems` pages, includes deleted, private, live, non-embeddable and duplicate items, and at least one video with `standard` thumbnails (frame tier `sd`) and one without (tier `mq`);
    - `bravo` / `PLfixtureBravo02`: readable, but every item is filtered out (`status: empty`);
    - `charlie` / `PLfixtureCharlie3`: listed, but `playlistItems.list` returns 404 (`status: failed`);
    - `delta` / `PLfixtureDelta04`: missing from `playlists.list`, so it is omitted.
  - Add `YOUTUBE_API_KEY=` with a comment to `.env.example`.
- Verify: `npm run test:site` (U17).
- Commit: `feat(watch): seed curated playlists and fixture list`

### Wave 2 (parallel lanes A, B, C, in worktrees; § 7)

#### Lane A: data (T4 to T7, one agent, four commits)

Files (lane scope): `src/lib/watch/{duration,youtube,normalize,load,env,fixtureFetch}.ts`, the matching `*.test.ts`, and `src/lib/watch/fixtures/api/*.json`.

- **T4 `duration.ts`**: `parseIsoDuration(s): number | null`, `formatDuration(sec): string` (`m:ss` or `h:mm:ss`) and `spokenDuration(sec): string`. U1.
  - Commit: `feat(watch): parse ISO 8601 video durations`
- **T5 `youtube.ts`**: client with an injected `fetch` and `sleep`.
  - Methods: `listPlaylists(ids)` (one batched call, with `fields` trimming), `listPlaylistItems(id, max)` (`maxResults=50`, follows `nextPageToken`, stops at `max`), `listVideos(ids)` (batches of 50, `part=snippet,contentDetails,status`).
  - Typed `YouTubeError {kind: 'quota' | 'key' | 'not-found' | 'forbidden' | 'network' | 'malformed', scope: 'global' | 'playlist', call, status: number, reason: string | null, apiMessage: string | null}`. `reason` comes from `error.errors[0].reason` and `apiMessage` from `error.message`, both redacted. Key errors follow § 2 (by reason, not status).
  - Two retries with backoff on network and 5xx errors.
  - The injected `fetch` is called with the URL and an `AbortSignal` only: no `headers` argument, never a `Referer` or `Origin` header.
  - The key is redacted from every error message and URL.
  - Tests: U2, U3, U5 (client side), U6, U18, U19.
  - Commit: `feat(watch): add YouTube Data API client with pagination and batching`
- **T6 `normalize.ts`**: API items become `WatchVideo` and `WatchPlaylist` with the § 2 filters (including `embeddable`), dropped counts by reason, durations as text, description cuts, cover `src`/`srcset` from `medium`, `high`, `standard` and `maxres`, and the frame tier. U4, U22.
  - Commit: `feat(watch): normalize and filter playlist videos`
- **T7 `load.ts`, `env.ts`, `fixtureFetch.ts`, fixture JSON**:
  - `loadWatchData({curated, client, log})` implements the § 2 outcome table and log lines through the injected `log`, and turns global errors into `mode: 'none'`.
  - `resolveMode(env)` returns mode, key and expect-key.
  - `fixtureFetch` serves `fixtures/api/*.json` by URL path and params, and returns typed error bodies: 404 `playlistNotFound` for Charlie, `error-quota.json` (403 `quotaExceeded`) for U5, `error-referer-blocked.json` (`{"error":{"code":403,"message":"Requests from referer <empty> are blocked.","errors":[{"reason":"forbidden"}]}}`) and `error-key-invalid.json` (400 `keyInvalid`) for U19 and U20.
  - All fixture values are invented (P1).
  - Tests: U5 end to end, U12, U13, U15, U20, U21.
- Lane verify: U1 to U6, U12, U13, U15 and U18 to U22 pass with no network. `grep -rn "AIza" src/lib/watch` prints nothing.
  - Commit: `feat(watch): orchestrate build-time load with per-playlist warnings`

#### Lane B: client pure logic (T8, one agent)

Files (lane scope): `src/lib/watch/{state,preview,frames,popup-position}.ts` and the matching `*.test.ts`.

- `state.ts`: `parseUrl(search, playlists)` and `toSearch(state)` per P3 and UI spec § 4.8. U8.
- `preview.ts`: `previewsEnabled(stored, osReduce, siteReduce)` (U9) and a cycler driven by an injected clock and image loader, using `timings.ts` (U10).
- `frames.ts`: `frameUrls(id, tier)` (`https://i.ytimg.com/vi/<id>/<tier>1.jpg` to `3`), `coverSrcset(cover)` and `isPlaceholder(naturalWidth)`. U11.
- `popup-position.ts`: `placePopup(card, popupSize, viewport, playerRect)` per UI spec § 4.3 (never above; returns `null` when it cannot avoid the player). U16.
- Verify: the modules touch no DOM globals at module load: `grep -n "^const.*document\|^const.*window" src/lib/watch/*.ts` prints nothing.
- Commit: `feat(watch): add URL state, preview gate, frame and popup helpers`

#### Lane C: privacy (T9, one agent)

Files (lane scope): `src/pages/privacy.astro`, `src/layouts/Base.astro` (line 2 comment only).

- Do:
  - Use the UI spec § 6 draft: scope the "no analytics or tracking scripts" paragraph with "One exception: the Watch page", and add a "Watching videos" section (`id="watch"`) covering `i.ytimg.com` images, the click-to-load `youtube-nocookie.com` player, the locally stored previews setting, YouTube API Services, the Google Privacy Policy (`https://policies.google.com/privacy`) and the YouTube Terms of Service (`https://www.youtube.com/t/terms`). The copy is a draft for Brandon (Q3).
  - Change the `Base.astro:2` comment to note the `/watch` exception.
  - Do not touch the petitions copy.
- Verify: `grep -c "policies.google.com/privacy" dist/privacy/index.html` prints at least 1.
- Commit: `docs(privacy): describe YouTube requests on the watch page`

### Wave 3 (serial, main checkout)

#### T10: Content collection and loader wiring

- Files: `src/content.config.ts` only.
- Do:
  - Add `watchPlaylists` with an inline loader `name: 'watch-youtube'`.
  - The loader calls `store.clear()`, reads the YAML (`src/content/watch/playlists.yaml`, or the fixture YAML in `fixture` mode) with `js-yaml`, then `watcher?.add` on the YAML path, then `loadWatchData`, then `parseData` and `store.set` per playlist (id = `slug`). It prints log lines with `console.warn`/`console.log`, not Astro's `logger`, so the `::warning` prefix starts the line.
  - The schema comes from `src/lib/watch/schema.ts`. Add it to `collections`.
  - Read the key from `process.env.YOUTUBE_API_KEY`. Check whether a key in root `.env` reaches it in a local build. If not, use `loadEnv(mode, process.cwd(), '')` from `vite` for that variable only. Never use a `PUBLIC_` name.
- Verify:
  - `npm run build` with no key: succeeds and logs `mode=none playlists=0 videos=0`.
  - `WATCH_DATA=fixture npm run build`: succeeds and logs the U21 lines.
  - `WATCH_DATA=fixture GITHUB_ACTIONS=true npm run build 2>&1 | grep -c "^::warning title=Watch page::"` prints at least 1 (Charlie).
  - `npm run check:types` reports 0 errors (`astro check` runs the content sync, so the loader runs there too).
- Commit: `feat(watch): add watchPlaylists content collection with YouTube loader`

#### T11: Page shell, EmptyState slot, stub components, client main, Playwright scaffold

- Files:
  - `src/pages/watch.astro`;
  - `src/components/EmptyState.astro` (this task is its only editor);
  - `src/components/watch/{WatchPlaylistTabs,WatchPlayer,WatchPanel,VideoThumb,VideoPopup,PreviewSwitch}.astro` (stubs);
  - `src/components/watch/client/{main,tabs,player,grid,popup,preview}.ts` (`main` real, the others no-op `init*`);
  - `playwright.config.ts`;
  - `tests/e2e/helpers.ts`;
  - `tests/e2e/watch-smoke.spec.ts`.
- Do:
  - `EmptyState.astro`: add an optional `<slot />` after the `<p>` (UI spec § 3.4). Check that its seven existing users (§ 1) render unchanged: build just before and just after the edit, and from each of the seven built pages extract only the `<div class="empty-state" ...>...</div>` fragments (where present) with `data-astro-cid-*` attributes stripped; the fragments must be identical. Compare fragments, not whole pages, because a peer adding research sources or a new hashed CSS file name can change the rest of the page between builds.
  - Page per UI spec § 3.3: `layout="wide"`, breadcrumb, h1 "Watch", `WATCH_LEDE` stub, `data-watch-mode`, the `.watch-layout` grid with rail and main column, the toolbar with the "Videos and images from YouTube." attribution and Terms of Service link, the `role="status"` live region (`watch-status`), the `data-watch-data` JSON block, and the `<noscript><style is:inline>` block (UI spec § 4.10). The page maps entries to `WatchPlaylistView` by adding `publishedText = formatPostDate(new Date(publishedIso))`. Server default is the first playlist with `status: ok`, else the first playlist.
  - `none` mode (no entries): render breadcrumb, h1, lede and `<div data-testid="watch-page-empty"><EmptyState message="These videos could not be loaded." /></div>`; no rail, player, switch, panels, popup or JSON block (P8).
  - Stubs with final props. Each renders the UI spec § 3.3 markup outline with its final ids, testids, roles and data attributes, because other lanes' tests run against it: tabs with `watch-tab` and `data-playlist`; the player `section` with `watch-player-frame`, `watch-play`, `watch-notice` and `watch-player-title`; panels with `watch-grid` or `watch-empty`; `VideoThumb` as the `<a href="https://www.youtube.com/watch?v=<id>&list=<youtubeId>">` with `watch-thumb`, `data-video-id`, `data-playlist`, `data-frame-tier` and the `.watch-thumb__media` span holding the cover `<img>` (the no-JS path); the popup shell; the switch shell. Also the sizing CSS other lanes measure: `.watch-player__frame` and `.watch-thumb__media` per UI spec § 7.2. Wave 4 lanes complete their own component's behaviour, copy and remaining CSS.
  - `main.ts`: reads the JSON (exits if absent), `parseUrl`, owns `WatchState`, applies § 4 "Startup and ownership", toggles `hidden` on panels by `data-playlist` on `watch:playlist`, calls `history.replaceState(toSearch(state))`, and announces a reader's playlist change (UI spec § 4.9). Wave 4 lanes do not edit `main.ts` or `watch.astro`.
  - `playwright.config.ts`:
    - `testDir: 'tests/e2e'`, Chromium only;
    - port `Number(process.env.WATCH_E2E_PORT ?? 4329)`, used for both `webServer.url` and `use.baseURL`, each `http://127.0.0.1:<port>` to match `--host`;
    - `webServer.command`: `npm run build && npm run preview -- --port <port> --host 127.0.0.1`, `env: { WATCH_DATA: 'fixture' }`, `reuseExistingServer: false` (the operator's `inv dev` holds 4321, and parallel lanes must never attach to another lane's server).
  - `helpers.ts`:
    - routes `https://i.ytimg.com/**` to generated images (480x270 for covers, 640x480 for `sd*`, 320x180 for `mq*`, and a 120x90 image with status 404 for a frame the fixture marks missing);
    - routes `https://www.youtube-nocookie.com/**` to a blank HTML page;
    - fails the test on any other external request;
    - records request URLs for assertions.
  - Smoke spec: the page loads; no `<iframe>`; no request to `youtube-nocookie.com` and no frame requests on load; the Delta tab is absent; the Charlie panel holds `watch-empty` with a "See the playlist on YouTube" link (the EmptyState slot works); with `javaScriptEnabled: false`, every panel is visible and cards link to youtube.com.
- Verify:
  - `npm run test:e2e` passes the smoke spec on port 4329 while `inv dev` keeps running on 4321.
  - A keyless `npm run build` gives `dist/watch/index.html` with `data-watch-mode="none"` and `data-testid="watch-page-empty"`.
  - The `EmptyState` diff above is clean.
- Commit: `feat(watch): add /watch page shell, client state and Playwright scaffold`

### Wave 4 (parallel lanes D to H, in worktrees; each lane owns only its listed files)

Every lane builds its component per the named UI spec sections and fills in its `client/<name>.ts`. It uses the § 4 testids, classes, timings and storage key, and writes its own spec file. Shared helpers (`tests/e2e/helpers.ts`, `contract.ts`, `timings.ts`, `types.ts`) are read-only for lanes; a lane that needs a change reports it to the orchestrator. Each lane runs Playwright on its own port (§ 7 table).

#### T12, lane D: Playlist tabs

- Files: `src/components/watch/WatchPlaylistTabs.astro`, `src/components/watch/client/tabs.ts`, `tests/e2e/watch-playlists.spec.ts`.
- Build: UI spec § 3.3 (tabs markup), § 4.6 (manual activation, roving `tabindex`, wrapping, Home and End), § 7.2 (`.watch-rail*`, `.watch-tab*`; sticky rail at 1120px and up). Selecting sets `aria-selected` and roving `tabindex`, then emits `watch:playlist`; `main.ts` (T11) shows and hides the panels.
- E2E: E1; a `?list=<slug>` deep link selects that tab; an unknown `list` falls back to the default and is removed from the URL; E6 (tab keys); the live region announces "<name>, <n> videos." and "<name>, no videos to show." for Bravo.
- Verify: `WATCH_E2E_PORT=4331 npm run test:e2e -- watch-playlists`.
- Commit: `feat(watch): playlist tabs with keyboard selection and deep links`

#### T13, lane E: Player

- Files: `src/components/watch/WatchPlayer.astro`, `src/components/watch/client/player.ts`, `tests/e2e/watch-player.spec.ts`.
- Build: UI spec § 3.3 (player markup, `CirclePlay` from `lucide-astro`), § 4.7 (events table), § 7.2 (`.watch-player*`, `.watch-notice`; style the inserted iframe with `:global(.watch-player__iframe)`). Play replaces the poster with the § 4 Embed iframe and focuses the title. On `watch:video` with `play: false`: swap the poster and text, remove any iframe, and show `watch-notice` only when `notice` is true. With `play: true`: the same swap, mark nothing itself (lane F marks the card), focus the title with `preventScroll: true`, then insert the iframe at once if the frame is at least `PLAYER_MIN_VISIBLE_RATIO` in view; otherwise `scrollIntoView` (`smooth`, or `auto` under a reduce setting) and insert it when an `IntersectionObserver` with threshold `0.5` fires. Emits `watch:play`. Show more and Back to video list per § 4.7.
- E2E: E2; clicking Play creates exactly one iframe with host `www.youtube-nocookie.com`, `autoplay=1` and no `referrerpolicy`; E7; E9; E11; E12; an unknown `v` shows `watch-notice` and the URL loses `v`.
- Verify: `WATCH_E2E_PORT=4332 npm run test:e2e -- watch-player`.
- Commit: `feat(watch): click-to-load nocookie player`

#### T14, lane F: Panels, thumbnails, card clicks and popup

- Files: `src/components/watch/{WatchPanel,VideoThumb,VideoPopup}.astro`, `src/components/watch/client/{grid,popup}.ts`, `tests/e2e/watch-grid.spec.ts`.
- Build:
  - UI spec § 3.3 (panel, thumb and popup markup), § 4.2 (card states), § 4.3 (popup rules, using `placePopup`), § 5 (panel empty and failed copy, the failed state's YouTube link in the `EmptyState` slot), § 7.2 (`.watch-panel*`, `.watch-grid`, `.watch-thumb*`, `.watch-popup*`).
  - `VideoThumb.astro` also carries the frame-layer CSS for lane G: `.watch-thumb__media :global(.watch-thumb__frame)` and `:global(.watch-thumb__frame.is-shown)` per UI spec § 7.2. It renders no frame `<img>` in server HTML.
  - `grid.ts`: an unmodified primary click or Enter on a card calls `preventDefault` and emits `watch:video` with `play: true`; modified and middle clicks keep the link. It sets `aria-current="true"` and unhides "Playing" on the card at once on `watch:video` with `play: true` (before the autoplay gate, UI spec § 4.7), and also on `watch:play` for the poster Play path. A `play: false` event marks nothing.
  - `popup.ts`: one shared popup, fine-pointer mouse only, `POPUP_OPEN_DELAY_MS` on rest, at once on keyboard focus, close rules per UI spec § 4.3.
- E2E (use `page.clock`): hover opens after 300ms; focus opens at once; Escape closes without moving focus; moving the pointer from card into popup keeps it open; scrolling closes it; a `hasTouch` context shows no popup; E8 (first-row card, no iframe); selecting a video updates `?v=` and `aria-current`; a modified click does not play.
- Verify: `WATCH_E2E_PORT=4333 npm run test:e2e -- watch-grid`.
- Commit: `feat(watch): video panels, thumbnails and hover popups`

#### T15, lane G: Preview switch and frame cycling

- Files: `src/components/watch/PreviewSwitch.astro`, `src/components/watch/client/preview.ts`, `tests/e2e/watch-preview.spec.ts`.
- Build:
  - UI spec § 3.3 (switch markup), § 4.4 (frame cycling), § 4.5 (switch rules), § 7.2 (`.watch-switch*`, copied from `.a11y-radio`).
  - The switch is shown only when `(hover: hover) and (pointer: fine)` matches. The effective state comes from `previewsEnabled` (D8). With nothing stored it follows live media-query and `data-motion` changes.
  - Cycling creates the two `img.watch-thumb__frame` layers (with `referrerpolicy="no-referrer"`, like the preloading `Image()` objects) inside the card's `.watch-thumb__media` on first preview, loads `frameUrls(id, data-frame-tier)` at `FRAME_LOAD_AT_MS`, sets `data-previewing` and `data-frame`, skips frames that error or are `isPlaceholder`, and stops on every UI spec § 4.4 stop event.
- E2E (use `page.clock`): E3 (one `sd` card and one `mq` card, checking the requested URL tier); keyboard focus on a card cycles too (mouse device); no frame requests before the first hover; E4; E5; a missing frame is skipped; E6 (switch keys); the switch is hidden in a `hasTouch` context.
- Verify: `WATCH_E2E_PORT=4334 npm run test:e2e -- watch-preview`.
- Commit: `feat(watch): hover preview switch and frame cycling`

#### T16, lane H: Post-build dist check

- Files: `scripts/check-watch-page.ts`.
- Do: model it on `scripts/check-reviewer-display.ts`. Read `dist/watch/index.html` and `data-watch-mode`. Checks:
  - B1: the page exists.
  - B2: no `AIza` anywhere in `dist/`, and, if `YOUTUBE_API_KEY` is set, its exact value nowhere in `dist/`. Never print the key.
  - B3: no `<iframe` on `/watch`.
  - B4: in `live` and `fixture` mode, the `watch-thumb` count is above zero and every thumb anchors to `https://www.youtube.com/watch`. In `none` mode, `watch-page-empty` is present, there are zero thumbs, and the script prints "skipped: no video data".
  - B5: `https://www.youtube.com/t/terms` is linked on `/watch` (in `live` and `fixture` mode), and `/privacy` links `https://policies.google.com/privacy`.
  - B6: in `fixture` mode, exactly the Alpha, Bravo and Charlie tabs in order, with the expected counts and statuses. In `live` mode an `empty` or `failed` playlist is a `::warning::`, not a failure (D4).
  - With `WATCH_CHECK_CONTEXT=deploy`, `fixture` mode is an error, so fixture data can never ship.
- Verify:
  - `WATCH_DATA=fixture npm run build && npm run check:watch` exits 0.
  - A keyless `npm run build && npm run check:watch` exits 0 with the skip line.
  - `WATCH_DATA=fixture npm run build && WATCH_CHECK_CONTEXT=deploy npm run check:watch` exits 1.
- Commit: `feat(watch): post-build check for /watch output and key leaks`

### Wave 5 (serial, main checkout)

#### T22: Cross-lane browser tests

- Files: `tests/e2e/watch-flows.spec.ts`.
- Do: test the flows that need two wave 4 lanes at once, on the merged main:
  - a card click with the player at least half in view inserts exactly one iframe at once;
  - E10 (autoplay gate after a card click far down the grid);
  - E8 with an iframe in the player;
  - Back to video list focuses the playing card;
  - poster Play marks the matching card `aria-current="true"`;
  - E11's tab-click half (poster follows a tab change until a video is loaded);
  - changing the tab closes an open popup.
- Verify: `npm run test:e2e` (all six spec files) on port 4329 with `inv dev` still on 4321.
- Commit: `test(watch): cross-component browser flows`

#### T17: Wire checks into npm, Invoke and CI; weekly scheduled deploy of main

- Files: `package.json` (append `&& npm run check:watch` to `check`), `tasks.py` (`check`: run `npm run check:watch` after `build(ctx)`), `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`.
- `ci.yml`, `check` job:
  - job-level `env: WATCH_DATA: fixture`;
  - add `npm run check:types` (currently missing; needed for the new TS);
  - add `npm run check:watch` after the build.
- `ci.yml`, new `e2e` job: `npm ci`, `npx playwright install --with-deps chromium`, `npm run test:e2e` (default port 4329).
- `deploy.yml`:
  - `on.schedule: - cron: '17 6 * * 1'` (Mondays 06:17 UTC). Keep `push` and `workflow_dispatch` as they are (T21 needs dispatch).
  - No job-level `if:` changes and no checkout changes (P7). A scheduled run checks out the default branch's latest commit and runs `verify`, `build` and `deploy` as a push does, so it deploys `origin/main` as it already stands, with refreshed YouTube data.
  - On the `npm run build` step only: `env: YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}` and `WATCH_EXPECT_KEY: '1'`. `GITHUB_ACTIONS` is already set by the runner, so warnings become annotations. No header or referrer configuration anywhere.
  - A new step after the build: `npm run check:watch` with the same key env and `WATCH_CHECK_CONTEXT: deploy`.
  - No other step gets the key.
- Verify:
  - `inv check` passes locally with no key.
  - `actionlint` if installed, else `python3 -c "import yaml,sys;[yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/ci.yml .github/workflows/deploy.yml`.
  - `uvx zizmor .github/workflows` reports nothing new compared with HEAD.
  - CI runs only after Brandon pushes (D15); the `check` and `e2e` results are read in T21.
- Commit: `ci(watch): build with fixtures, run browser tests, deploy weekly`

#### T18: Architecture docs and roadmap

- Files: `docs/architecture/site.md` (collection, loader modes, log lines, client modules, test layers), `docs/architecture/ci-deploy.md` (secret, weekly cron that rebuilds main like a push deploy, `check:watch`, `e2e` job, Playwright port), `docs/v1.0.0-roadmap.md` (tick "Build the page"; check `git diff` on it first, as in T0).
- Verify: `npm run lint:md`, and every path named in the docs exists.
- Commit: `docs(architecture): document the watch page data flow and CI`

### Wave 6 (serial, needs Brandon)

#### T19: Live key verification (local)

- Prerequisite: the key is in root `.env` on Brandon's machine (it is API-restricted only, D14, and works locally).
- Steps:
  1. `npm run build`. Expect `data-watch-mode="live"`, no global warning, three `fetched` lines and `mode=live playlists=3`.
  2. Check the counts: `PLXFc9I7KsRUk` at most 4, FAR.AI and Oxford at most 50 each (capped from 63 and 53), and the dropped and not-embeddable counts look sane. Record the three lines in the handoff note.
  3. `npm run check:watch` with the key exported from `.env` in a subshell, so B2 runs with the exact key. Never echo the key.
- Commit: none, unless `max_videos` or a slug changes: `chore(watch): adjust curated playlists after live check`.

#### T21: Manual-dispatch deploy verification (ask Brandon first)

- Prerequisites: Brandon has pushed main (which itself triggers a push deploy, D15) and approves the dispatch.
- Do:
  1. `gh workflow run deploy.yml --ref main` (or Actions > Deploy to GitHub Pages > Run workflow).
  2. `gh run watch` until it finishes, then `gh run view <id> --log` and filter for the `build` job's build step.
- Verify:
  - a `[watch loader] fetched <id>: <n> videos (dropped: <k>, not embeddable: <e>)` line for each of `PLXFc9I7KsRUk`, `PLpvkFqYJXcreU5HqW6aUYeppYPG8aBRZ_` and `PLf4lTwFHevBuvTDX4m8N5WVAX62IkhXJ7`, each with n > 0;
  - the summary `mode=live playlists=3 videos=<total>`;
  - no `::warning title=Watch page::` annotation in the run's Annotations list. If one appears, confirm it renders as an annotation (this also settles the § 1 unverified log-prefix question);
  - green `verify` (`check` and `e2e` jobs) and `check:watch` steps.
- If it fails: the warning names the call, HTTP status, reason and API message. A `forbidden` with "referer" in the message, or `keyInvalid`, means the key is misconfigured (RISK-15). The deploy still succeeds with the empty state (D4).
- Then: open the deployed `/watch` and confirm the live data renders.
- Commit: none, or `docs(plans): record watch page deploy verification` (docs only).

#### T20: Manual browser check and first deploy (ask Brandon first)

- Run the § 8 manual checklist on the local live build (`npm run preview`, on a port other than 4321).
- The first deploy happens when Brandon pushes main (D15); T21 covers the key-bearing dispatch.
- After the push that ships T17, confirm the next Monday scheduled run: `verify`, `build` and `deploy` are green on main HEAD, and the log shows `mode=live playlists=3`. Add a calendar reminder for RISK-1.
- Tick the roadmap's seed item. Ask Brandon whether to move the plan and UI spec to `docs/plans/completed/` (AGENTS.md Plans rule 5).

## 7. Parallelization

Waves run in order. Serial waves (0, 1, 3, 5) run in the main checkout and stage explicit paths only. Parallel lanes (waves 2 and 4) run in git worktrees.

**Lane procedure**

1. The orchestrator creates each worktree from local main after the previous wave is committed there: `git worktree add -b watch/<lane> ../site-wt-<lane> main`. Do not use harness-made worktrees: they branch from origin, which lacks 178 local commits and the promoted plan. The sibling directories are outside the session's project directory, so Brandon grants them with `/add-dir` before the wave (Q4); otherwise lanes stall on write prompts. No gate registration is needed in a lane: sibling worktree paths are not gated, and T0's record in the main checkout covers the item (§ 1).
2. The lane, working only through its worktree's absolute path `<wt>` (subagent Bash calls reset to the main checkout, and `cd` may not be combined with another command):
   - `npm --prefix <wt> ci`; Chromium is already in Playwright's shared cache from T1;
   - Edit and Write only on paths under `<wt>`;
   - before every commit: `npm --prefix <wt> run check:types`, `npm --prefix <wt> run test:site`, `npm --prefix <wt> run build`, and its own e2e spec on its own port (`WATCH_E2E_PORT=<port> npm --prefix <wt> run test:e2e -- <spec>`); the pre-commit hook skips in a fresh worktree (§ 1);
   - `git -C <wt> status` shows branch `watch/<lane>`, then `git -C <wt> add <own files>` (table below) and `git -C <wt> commit`.
3. Lanes do not edit this plan, the roadmap or `handoff/`. They report results and any helper change they need to the orchestrator.
4. After the wave, the orchestrator merges each lane branch into main in the main checkout (`git merge --no-ff watch/<lane>`, or `git cherry-pick` for single commits), runs `inv check` (and `npm run test:e2e` after wave 4, since `inv check` runs no browser tests), runs `/simplify` once for the wave, ticks `## Status`, updates the handoff note, then removes the worktrees (`git worktree remove ../site-wt-<lane>`, `git branch -d watch/<lane>`).

| Wave | Lane | Tasks | Where | File scope (exclusive) | E2E port | Depends on |
|------|------|-------|-------|------------------------|----------|-----------|
| 0 | orchestrator | T0 | main checkout | `docs/plans/watch-page.md`, `docs/plans/watch-page-ui-spec.md`, `docs/v1.0.0-roadmap.md` | n/a | none |
| 1 | serial | T1, T2, T3 | main checkout | `package.json`, `package-lock.json`, `src/lib/watch/{types,contract,timings,schema}.ts`, `schema.test.ts`, `playlists.test.ts`, `src/content/watch/playlists.yaml`, `src/lib/watch/fixtures/playlists.fixture.yaml`, `.env.example` | n/a | T0 |
| 2 | A data | T4 to T7 | `../site-wt-a` | `src/lib/watch/{duration,youtube,normalize,load,env,fixtureFetch}.ts` and their tests, `src/lib/watch/fixtures/api/` | n/a | wave 1 |
| 2 | B client logic | T8 | `../site-wt-b` | `src/lib/watch/{state,preview,frames,popup-position}.ts` and their tests | n/a | wave 1 |
| 2 | C privacy | T9 | `../site-wt-c` | `src/pages/privacy.astro`, `src/layouts/Base.astro` | n/a | wave 1 |
| 3 | serial | T10, T11 | main checkout | `src/content.config.ts`, `src/pages/watch.astro`, `src/components/EmptyState.astro`, `src/components/watch/**` (stubs), `playwright.config.ts`, `tests/e2e/helpers.ts`, `tests/e2e/watch-smoke.spec.ts` | 4329 | wave 2 |
| 4 | D tabs | T12 | `../site-wt-d` | `WatchPlaylistTabs.astro`, `client/tabs.ts`, `tests/e2e/watch-playlists.spec.ts` | 4331 | wave 3 |
| 4 | E player | T13 | `../site-wt-e` | `WatchPlayer.astro`, `client/player.ts`, `tests/e2e/watch-player.spec.ts` | 4332 | wave 3 |
| 4 | F grid | T14 | `../site-wt-f` | `WatchPanel.astro`, `VideoThumb.astro`, `VideoPopup.astro`, `client/grid.ts`, `client/popup.ts`, `tests/e2e/watch-grid.spec.ts` | 4333 | wave 3 |
| 4 | G preview | T15 | `../site-wt-g` | `PreviewSwitch.astro`, `client/preview.ts`, `tests/e2e/watch-preview.spec.ts` | 4334 | wave 3 |
| 4 | H dist check | T16 | `../site-wt-h` | `scripts/check-watch-page.ts` | n/a | wave 3 |
| 5 | serial | T22, T17, then T18 | main checkout | `tests/e2e/watch-flows.spec.ts`, `package.json`, `tasks.py`, `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`, `docs/architecture/site.md`, `docs/architecture/ci-deploy.md`, `docs/v1.0.0-roadmap.md` | 4329 | wave 4 |
| 6 | serial | T19, T21, T20 (in that order) | main checkout | `src/content/watch/playlists.yaml` (if needed) | n/a | wave 5, Brandon |

Single owners: `src/content.config.ts` (T10), `src/pages/watch.astro`, `client/main.ts` and `src/components/EmptyState.astro` (T11), each workflow file (T17), and `package.json` (T1, then T17).

Cross-lane coupling between F and G: lane F owns the thumb markup (G tests against the T11 stub's `.watch-thumb__media` and `data-frame-tier`) and the frame-layer CSS (`:global(.watch-thumb__frame)`); lane G creates the frame `<img>` layers at runtime and reads `CLASS.thumbMedia`, `CLASS.thumbFrame`, `CLASS.frameShown` and `data-frame-tier` from the contract. Neither edits the other's files. Lane E and F meet only through bus events: F emits `watch:video` and marks the playing card at once; E emits `watch:play` when an iframe goes in.

## 8. Verification

**Automated (local)**

| Command | Expected |
|---------|----------|
| `npm run test:site` | All pass, including U1 to U13, U15 to U22 under `src/lib/watch/`. No network: the tests pass with networking off. |
| `npm run check:types` | 0 errors, 0 warnings for new files |
| `npm run build` (no key) | Succeeds. `mode=none playlists=0 videos=0`. `dist/watch/index.html` has `data-watch-mode="none"` and `watch-page-empty`. |
| `WATCH_DATA=fixture npm run build && npm run check:watch` | Succeeds. The U21 log lines. The check exits 0. |
| `npm run test:e2e` | All six spec files pass on Chromium on port 4329, with `inv dev` still running on 4321 |
| `EmptyState` before/after fragment check (T11) | The seven research pages' `.empty-state` fragments are identical |
| `inv check` (also what the pre-commit hook runs) | Passes with no key |

**After Brandon pushes (D15)**

| Run | Expected |
|-----|----------|
| Push deploy (`verify`, `build`, `deploy`) | Green, including the `check` job's check:types and check:watch and the `e2e` job |
| Manual `workflow_dispatch` deploy (T21) | Green. The build log shows a `fetched ... videos` line with n > 0 for each seed playlist and `mode=live playlists=3`. No watch warning annotation. `check:watch` runs with `WATCH_CHECK_CONTEXT=deploy`. |
| First scheduled run (T20) | Builds main HEAD; `verify`, `build` and `deploy` green; `mode=live playlists=3` |

**Manual browser check** (live build, then production), at 375px (phone), 900px (tablet) and 1280px (desktop), plus the 1119px/1120px rail switch:

- [ ] All three seed playlists appear in D11 order, with name, creator and editor description.
- [ ] Thumbnails show a two-line title caption and a duration badge. There is no horizontal scroll at 375px.
- [ ] No iframe and no `youtube-nocookie.com` request before Play (DevTools Network).
- [ ] No frame request before the first hover. Frames cycle on hover and stop on leave. A card with `data-frame-tier="sd"` requests `sd*.jpg`; others request `mq*.jpg`.
- [ ] The switch: Off persists across reload. With OS reduce motion on, the default is Off with the hint. Site Motion: Reduce behaves the same.
- [ ] Popups: 300ms hover delay, open on keyboard focus, Escape closes them, they never cover the player (also on first-row cards), and none appear on a touch device.
- [ ] Clicking a card far down the grid scrolls the player into view and starts playback only once the player is at least half on screen.
- [ ] Keyboard only: skip link, then tabs (arrows plus Enter), then Play, then "Watch on YouTube", then the switch, then thumbnails. Focus is always visible.
- [ ] Deep links: `?list=far-ai-research-highlights&v=<id>` opens that poster. A bogus `v` shows the notice. A bogus `list` falls back.
- [ ] Copying the URL after playing a video and opening it in a new tab shows the same poster, without autoplay.
- [ ] All four themes (dark, light, both high-contrast). The player box stays black and text contrast holds.
- [ ] `/privacy` shows the `/watch` exception with the YouTube Terms of Service and Google Privacy Policy links.
- [ ] `/watch` is not in the nav.
- [ ] With JS disabled, every playlist's panel shows and thumbnails are links to youtube.com.

## 9. Risks

| ID | Risk | Mitigation |
|----|------|-----------|
| RISK-1 | The 30-day rule is breached if deploys stop. GitHub disables scheduled workflows in a public repo after 60 days without activity (unverified for this repo). | Weekly cron, plus a calendar check. A failed API call publishes the empty state, which also removes the stale data from the live site. |
| RISK-2 | A seed playlist becomes unreadable (made private or deleted). | Per-playlist warning; shown as failed or omitted (U12, U13); the deploy stays green; B6 warns. |
| RISK-3 | The secret is missing or expired, so deploys silently publish the empty state. | `WATCH_EXPECT_KEY=1` prints a `::warning::` on every deploy without a key. B6 warns on empty playlists. The warning carries the API reason and message, so a blocked or invalid key is identifiable from the annotation alone. |
| RISK-4 | Key leak through logs, client code or commits. | The key is only on the deploy build and check steps. No `PUBLIC_` prefix. Redaction (U6). B2 exact-value and `AIza` scan. The key is restricted to YouTube Data API v3. |
| RISK-5 | Frame URLs are undocumented and may change. `sd` 404s on low-resolution uploads, and the 404 returns a 120x90 image. | Covers use documented API thumbnails. The tier is `sd` only when the API returned `standard`. `isPlaceholder` and `onerror` skip failed frames. Frames are an enhancement. |
| RISK-6 | Privacy and ethos: `i.ytimg.com` requests on page load contradict the site-wide "no third-party requests" stance. | Privacy page exception (T9), the `Base.astro:2` comment fix, click-to-load nocookie embed, and frames only on hover. |
| RISK-7 | Overlay rule (YouTube Required Minimum Functionality): a popup covering the player, or autoplay while the player is mostly off screen. | `placePopup` never places above and refuses to open over the player (U16, E8). Autoplay waits for half visibility (E10). |
| RISK-8 | Page weight with 50+ thumbnails per playlist. | `srcset` and `sizes`, `loading="lazy"` except the first two cards, hidden non-selected panels, `max_videos`. |
| RISK-9 | Scheduled runs go through `verify` (P7), so a flaky e2e test or a red main (`check`, `e2e` or `lint-content`) blocks the weekly refresh. The last good deploy stays live, so a main that stays red for about four weeks serves API data past 30 days. | Timer tests use `page.clock`, not real waits. Re-run a failed scheduled run; fix a red main within the week. The RISK-1 calendar check also catches a run of failed Mondays. |
| RISK-10 | `astro check` and every pre-commit build call the API when a local key is set. | About 7 quota units per load. An offline machine gets the empty state plus a warning, never a failure. |
| RISK-11 | The root `.env` may not reach `process.env` in the loader. | Checked in T10, with a `loadEnv` fallback. |
| RISK-13 | Region- or age-restricted videos fail to play in the embed. | Accept for v1. "Watch on YouTube" is always shown under the player. |
| RISK-14 | Stale local `.astro` data store holding API data. | The loader always calls `store.clear()` and refetches. `.astro/` is gitignored. |
| RISK-15 | The key gets an HTTP referrer restriction again, so server-side calls fail with `403 forbidden: Requests from referer <empty> are blocked.` The deploy succeeds with an empty page. | D14. The warning shows the reason and message verbatim (U19, U20). T21 checks the dispatch log for per-playlist counts. Never spoof a Referer (U18). |
| RISK-16 | Any push to main before wave 6 deploys a partial /watch (keyless before T17, so the page-level empty state). It is not in the nav but is in the sitemap. | Brandon chooses when to push (D15). The stub lede is visible, so a partial page is recognisable. |
| RISK-17 | Parallel lanes collide on the Playwright port or a shared server. | `reuseExistingServer: false` and a port per lane (§ 7). |

## 10. Open items for Brandon

- Q1: The intro lede (`WATCH_LEDE`, also the page `description`), the three editor descriptions, and the three slugs (`dangerous-robot`, `far-ai-research-highlights`, `oxford-ethics-colloquia`). Slugs appear in shared URLs, so settle them before the first deploy.
- Q2: Should the site's Motion: Reduce setting also default previews to Off (D8, design DEC-7), or only the OS setting?
- Q3: Review the privacy page copy (UI spec § 6 draft, implemented in T9).
- Q4: The key is ready (API-restricted only, works locally, repository secret set). Approve the pushes and the T21 `workflow_dispatch` run when wave 5 is done. Before wave 2, grant the sibling worktree directories (`/add-dir ../site-wt-a` and so on, one per lane); agents cannot run that command, and a lane that hits a write prompt stalls.
- Q6: Resolved 2026-10-12 (orchestrator): log lines print the playlist ID and counts only, never API titles, so Actions logs (90-day retention) hold no YouTube API data.

## Edit history

| Date | Type | Who | Notes |
|------|------|-----|-------|
| 2026-10-12 | drafted | agent (claude-opus-5-5) | Initial plan from both research docs, Brandon's decisions and the private-playlist update. UI spec reconcile pending. |
| 2026-10-12 | revised | agent (claude-opus-5-5) | Added D14, the no-Referer rule, API reason and message in warnings, per-playlist log lines, U18 to U21, T21 manual-dispatch verification, RISK-15. |
| 2026-10-12 | revised | agent (claude-opus-5-5) | Reconciled with the UI spec: final testids, classes, timings, storage key and breakpoints frozen in § 4; `sd`/`mq` frame tiers; `?list=` uses a YAML `slug`; non-embeddable videos dropped at build; autoplay waits for half visibility (E10); EmptyState slot owned by T11. Removed the editor fallback (all seed playlists are public and readable). Key-error mapping by reason, global-error log lines. Cron rebuilds the latest beta tag and skips `verify` on schedule. Worktree lane procedure from local main, per-lane Playwright ports, no PR workflow; remote steps ask Brandon first. Inline test tables, overrides to the UI spec, T0 promotes the UI spec. |
| 2026-10-12 | reviewed | agent (claude-opus-5-5), fresh-eyes review | Reviewed this plan and the UI spec end to end against the repo; see Review history. |

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-12 | agent (claude-opus-5-5), fresh-eyes review | This plan and `watch-page-ui-spec.md` end to end; cited paths, scripts, workflows, `content.config.ts`, Base, EmptyState, A11yControl and the release gate checked against the repo | Scheduled runs now rebuild main like a push deploy (D5, P7, T17, T18, T20, § 8; tag logic, RISK-12 and Q5 removed; RISK-9 covers a red main blocking the refresh). Froze startup and bus ownership in § 4 so wave 4 controllers get arrival state. T11 stubs carry the full markup outline. Cross-lane flows moved to new T22. Added E11 and E12 and more popup and preview cases. Corrected the gate and worktree facts and the lane procedure (absolute worktree paths, no per-lane gate record, e2e after the wave 4 merge). Workflow-command escaping for `::warning`. Fixed stale UI spec text (slug field, private playlist, keyless empty state). Added Q6 (API titles in Actions logs). P8 and P9 accepted. |

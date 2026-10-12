# Watch page: UI spec
Status: reviewed, 2026-10-12. Roadmap item SITE-AM (Watch page), `docs/v1.0.0-roadmap.md`. Inputs: `docs/plans/drafts/watch-page-research-design.md` (design research, "DR doc" below) and `docs/plans/drafts/watch-page-research-architecture.md` (architecture research, "arch doc" below). Brandon's decisions are in the Decisions table of `docs/plans/watch-page.md`. The research docs are local drafts (gitignored); the plan and this spec carry everything implementers need. This spec covers the page's UI only; data loading, the loader modes and CI live in the architecture plan.

## 1. Where the research docs disagreed, and what this spec uses

| ID | Topic | DR doc | Arch doc | This spec | Why |
|---|---|---|---|---|---|
| CF-1 | Base layout | `wide` | `bare` | `layout="wide"` | Page must look like the site; `bare` drops width and padding (DR doc drift flag DR-3, "immersive" dark page) |
| CF-2 | Preview gate | Explicit choice beats reduce-motion | Switch AND no reduce-motion (switch cannot override) | Explicit choice wins | Brandon: reduce-motion turns previews off by default, "switch can re-enable" |
| CF-3 | Storage key | `dr-watch-previews`, written only on explicit choice | `dr-watch-preview`, default `on` | `dr-watch-previews`, values `on` / `off`, written only on explicit choice | No stored value is needed to apply the reduce-motion default |
| CF-4 | Frame size | `sd1`-`sd3` | `maxres` if present, else `mq`; avoid `sd` | Tier chosen at build: `sd` when the API returned `thumbnails.standard`, else `mq` | `sd` 404s on low-res uploads, so the tier must come from build data; `sd` is about a third the bytes of `maxres` frames (DR doc measurements) and cards are about 500 CSS px wide |
| CF-5 | Thumbnail element | `<button>` | `<a href="https://www.youtube.com/watch?v=…&list=…">` intercepted by JS | Anchor, intercepted | Works without JS; modified clicks still open YouTube; arch dist check B4 expects anchors |
| CF-6 | `?list=` value | YouTube playlist ID | Curated slug | Curated slug (`slug` in `playlists.yaml`) | Short, readable, stable if a playlist ID is swapped |
| CF-7 | Non-embeddable video | Show it, explain in the player | Drop at build | Drop at build | One fewer player state; count reflects what is shown |
| CF-8 | API failure at deploy | n/a | `required` mode fails the build | Empty state, deploy succeeds | Brandon's decision |
| CF-9 | Hotlink vs self-host images | Self-host preferred | Hotlink | Hotlink from `i.ytimg.com` | Brandon's decision |
| CF-10 | Popup placement fallback "above" | Allowed | Popups must never overlap the player (YouTube Required Minimum Functionality, policy III.I.6) | Popup top is clamped below the player box (§ 4.3) | Policy rule |

## 2. Layout

Chosen: DR doc OPT-A (player above the grid, playlist rail left). It keeps all three parts on one page, needs no modal, and a deep link shows a poster instead of opening a dialog on load.

Breakpoints reuse values already in `src`: 640px (`src/styles/global.css:81`), 1120px (`src/components/PageHeader.astro:160`). Root font size is 18px by default and 20px at Large (`src/layouts/Base.astro:126`), so rem widths below assume 18px.

| Range | Name | Rail | Grid |
|---|---|---|---|
| 1120px and up | Desktop | Left column `15rem`, sticky | 2 columns |
| 641 to 1119px | Tablet | Stacked list above the player, full width | 2 columns |
| 640px and down | Phone | Stacked list above the player | 1 column |

Width check (18px root, `.content` padding 1.5rem each side, 1rem at 540px and down, `src/layouts/Base.astro:533-541`, `:725-731`): at 1440px the main column is about 1080px, so 2 cards of about 525px. At 1120px, 2 cards of about 365px. At 375px, one card of about 320px.

### Desktop (1120px and up)

```
+--------------------------------------------------------------------------+
| site nav                                                                 |
+--------------------------------------------------------------------------+
| Home / Watch                                                             |
| Watch                                                          (h1)      |
| Intro: TBD, Brandon to write.                                  (.lede)   |
|                                                                          |
| PLAYLISTS -------  +----------------------------------------------------+|
| | Dangerous Robot  |                                                    ||
| | <channel name>   |            PLAYER, 16:9, black box                 ||
| | Short descrip-   |          poster image      ( > Play )              ||
| | tion, 3 lines    |                                                    ||
|                    +----------------------------------------------------+|
|   AI Safety -      | Video title                          (h2, Georgia) |
|   Research High... | Channel name   22:58   NOVEMBER 3, 2025            |
|   FAR.AI           | Description, 3 lines ...                          |
|   Short descr...   | Show more                                         |
|                    | Watch on YouTube     Back to video list            |
|   Colloquia and    |                                                    |
|   Lectures         | -------------------------------------------------- |
|   Institute for... | Videos and images from YouTube.   HOVER PREVIEWS   |
|   Short descr...   | YouTube Terms of Service          [ On | Off ]     |
|                    |                                                    |
|   (rail sticky)    | Dangerous Robot (h2)   4 VIDEOS                    |
|                    | +-----------------------+ +-----------------------+|
|                    | |                       | |                       ||
|                    | |    thumbnail 16:9     | |    thumbnail 16:9     ||
|                    | |                22:58  | |                10:20  ||
|                    | +-----------------------+ +-----------------------+|
|                    | Title, up to 2 lines      Title, up to 2 lines     |
|                    | PLAYING                                            |
+--------------------------------------------------------------------------+
| footer                                                                   |
```

### Tablet (641 to 1119px)

```
+----------------------------------------------------+
| Home / Watch                                       |
| Watch                                              |
| Intro: TBD, Brandon to write.                      |
| PLAYLISTS ---------------------------------------- |
| | Dangerous Robot           <channel name>         |
| | Short description, 2 lines                       |
|   AI Safety - Research Highlights   FAR.AI         |
|   Short description, 2 lines                       |
|   Colloquia and Lectures   Institute for Ethics... |
|   Short description, 2 lines                       |
| +------------------------------------------------+ |
| |            PLAYER 16:9     ( > Play )          | |
| +------------------------------------------------+ |
| Video title / meta / description / links           |
| ------------------------------------------------   |
| Videos and images from YouTube.  HOVER PREVIEWS    |
| YouTube Terms of Service         [ On | Off ]      |
| Dangerous Robot (h2)  4 VIDEOS                     |
| +---------------------+ +---------------------+    |
| |  thumbnail   22:58  | |  thumbnail   10:20  |    |
| +---------------------+ +---------------------+    |
| Title, 2 lines          Title, 2 lines             |
+----------------------------------------------------+
```

The switch shows on tablets only when the device has a mouse (§ 4.5).

### Phone (640px and down)

```
+-----------------------------+
| Home / Watch                |
| Watch                       |
| Intro: TBD, Brandon ...     |
| PLAYLISTS ----------------- |
| | Dangerous Robot           |
| | <channel name>            |
| | Description, 2 lines      |
|   AI Safety - Research H... |
|   FAR.AI                    |
|   Description, 2 lines      |
|   Colloquia and Lectures    |
|   Institute for Ethics...   |
|   Description, 2 lines      |
| +-------------------------+ |
| | PLAYER 16:9 (min 200px  | |
| | tall)        ( > Play ) | |
| +-------------------------+ |
| Video title                 |
| Channel  22:58  date        |
| Watch on YouTube            |
| --------------------------- |
| Videos and images from      |
| YouTube. YouTube Terms ...  |
| Dangerous Robot  4 VIDEOS   |
| +-------------------------+ |
| |  thumbnail       22:58  | |
| +-------------------------+ |
| Title, 2 lines              |
| ...                         |
+-----------------------------+
```

On phones the tablist shows name, creator and a 2-line description; the player keeps a 200px minimum height (YouTube's 200x200 minimum; a 16:9 box is only about 160px tall at 320px width).

## 3. Components

### 3.1 Files

| Path | New or changed | Role |
|---|---|---|
| `src/pages/watch.astro` | New | Page: reads collections, builds the view model, lays out the parts, emits the JSON payload |
| `src/components/watch/WatchPlaylistTabs.astro` | New | Rail: section label plus `role="tablist"` |
| `src/components/watch/WatchPlayer.astro` | New | Poster, Play button, title, meta, description, links |
| `src/components/watch/WatchPanel.astro` | New | One `role="tabpanel"` per playlist: heading, count, grid or empty state |
| `src/components/watch/VideoThumb.astro` | New | One card: anchor, cover image, duration badge, title, hidden description |
| `src/components/watch/VideoPopup.astro` | New | One shared, visual-only popup shell |
| `src/components/watch/PreviewSwitch.astro` | New | "Hover previews: On / Off" radiogroup and hint |
| `src/components/watch/watch-client.ts` | New | Thin DOM wiring; imports pure logic from `src/lib/watch/` |
| `src/lib/watch/state.ts`, `preview.ts`, `frames.ts`, `duration.ts` | New (named in arch doc § 5) | URL state, preview rule and cycler, frame URLs, duration text |
| `src/lib/watch/popup-position.ts` | New (this spec) | Pure `placePopup(card, popupSize, viewport, playerRect)`; unit tested |
| `src/lib/watch/timings.ts` | New (this spec) | Named timing constants (§ 4.1) |
| `src/components/EmptyState.astro` | Changed | Add an optional `<slot />` (§ 3.4) |
| `src/pages/privacy.astro` | Changed | /watch exception (§ 6) |

### 3.2 View model (what the components need from the data side)

| Type | Field | Notes |
|---|---|---|
| `WatchPlaylistView` | `slug` | `slug` from `playlists.yaml`; used in `?list=` and test hooks |
| | `youtubeId` | For YouTube links |
| | `name` | API title (no YAML fallback; a playlist with no API title is omitted) |
| | `creator?` | YAML `creator`, else API `channelTitle` |
| | `description` | YAML, max 200 chars; if empty, API description cut at a word boundary to 200 chars |
| | `status` | `ok`, `empty` (no public videos), `failed` (no data this build) |
| | `videos` | `WatchVideoView[]`, playlist order |
| `WatchVideoView` | `id` | 11-char video ID |
| | `title`, `channel` | Video's own channel, not the playlist owner |
| | `durationText`, `durationSpoken` | `22:58` and `22 minutes 58 seconds`; both empty when unparseable |
| | `publishedIso`, `publishedText` | `publishedText` via `formatPostDate` (`src/lib/writing.ts:21`, "November 3, 2025"), called at build only |
| | `description` | Plain text, cut to 500 chars with an ellipsis at build |
| | `cover` | `{ src, srcset }` from API `snippet.thumbnails` (`medium` 320w, `high` 480w, `standard` 640w, `maxres` 1280w when present) |
| | `frameTier` | `sd` or `mq` (frame size conflict, CF-4 in § 1) |

The page embeds the view model once with `<script type="application/json" data-watch-data set:html={jsonForScript(payload)}>` (pattern from `src/components/ShouldIDecisionTree.astro:50`, helper `src/lib/jsonForScript.ts`).

### 3.3 Markup outlines

**`src/pages/watch.astro`** (props: none)

```astro
<Base title="Watch" layout="wide">  <!-- description prop omitted until the intro is written -->
  <div class="watch" data-testid="watch-page">
    <Breadcrumb crumbs={[{ label: 'Home', href: '/' }, { label: 'Watch' }]} />
    <h1>Watch</h1>
    <p class="lede" data-testid="watch-lede">{WATCH_LEDE}</p>  <!-- const WATCH_LEDE = 'Intro: TBD, Brandon to write.' -->
    <noscript><style>/* § 4.10 */</style></noscript>
    <div class="watch-layout">
      <div class="watch-rail"><WatchPlaylistTabs playlists selectedSlug /></div>
      <div class="watch-main">
        <WatchPlayer video={initialVideo} playlist={initialPlaylist} />
        <div class="watch-toolbar">
          <p class="watch-attribution">Videos and images from YouTube. <a href="https://www.youtube.com/t/terms">YouTube Terms of Service</a></p>
          <PreviewSwitch />
        </div>
        {playlists.map((p) => <WatchPanel playlist={p} selected={p.slug === selectedSlug} eagerFirstRow={p.slug === selectedSlug} />)}
      </div>
    </div>
    <VideoPopup />
    <p class="sr-only" role="status" aria-live="polite" data-testid="watch-status"></p>
    <script type="application/json" data-watch-data set:html={payload} />
  </div>
</Base>
<script>import { initWatch } from '../components/watch/watch-client'; initWatch();</script>
```

Server-side default: the first playlist (order: Dangerous Robot, FAR.AI, Oxford) whose `status` is `ok`. Tab order never changes.

**`WatchPlaylistTabs.astro`** (props: `playlists: WatchPlaylistView[]`, `selectedSlug: string`)

```html
<div class="watch-rail__head"><span class="watch-rail__label" id="watch-playlists-label">Playlists</span><span class="watch-rail__line" aria-hidden="true"></span></div>
<div class="watch-tabs" role="tablist" aria-labelledby="watch-playlists-label" aria-orientation="vertical" data-testid="watch-tablist">
  <button type="button" role="tab" class="watch-tab" id="watch-tab-{slug}"
          aria-selected="true|false" aria-controls="watch-panel-{slug}" tabindex="0|-1"
          aria-labelledby="watch-tab-{slug}-name" aria-describedby="watch-tab-{slug}-creator watch-tab-{slug}-desc"
          data-testid="watch-tab" data-playlist="{slug}">
    <span class="watch-tab__name" id="watch-tab-{slug}-name">{name}</span>
    <span class="watch-tab__creator" id="watch-tab-{slug}-creator">{creator}</span>  <!-- omitted when no creator; drop its id from aria-describedby -->
    <span class="watch-tab__desc" id="watch-tab-{slug}-desc">{description}</span>
  </button>
</div>
```

**`WatchPlayer.astro`** (props: `video: WatchVideoView | null`, `playlist: WatchPlaylistView | null`; renders `hidden` when `video` is null)

```html
<section class="watch-player" aria-labelledby="watch-player-title" data-testid="watch-player" data-video-id="{id}" data-playlist="{slug}">
  <p class="watch-notice" data-testid="watch-notice" hidden>That video is no longer in this playlist.</p>
  <div class="watch-player__frame" data-testid="watch-player-frame">
    <button type="button" class="watch-player__poster" aria-label="Play: {title}" data-testid="watch-play">
      <img class="watch-player__img" src srcset sizes alt="" fetchpriority="high" decoding="async" referrerpolicy="no-referrer">
      <span class="watch-player__play" aria-hidden="true"><CirclePlay size={28} /> Play</span>
    </button>
    <!-- after a click the button is replaced by:
    <iframe class="watch-player__iframe" data-testid="watch-iframe"
            src="https://www.youtube-nocookie.com/embed/{id}?autoplay=1&rel=0"
            title="{title} (YouTube video)"
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>
    No referrerpolicy attribute on the iframe (YouTube "Error 153"). -->
  </div>
  <h2 class="watch-player__title" id="watch-player-title" tabindex="-1" data-testid="watch-player-title">{title}</h2>
  <p class="watch-player__meta" data-testid="watch-player-meta">
    <span class="watch-player__channel">{channel}</span>
    <span class="watch-player__duration">{durationText}</span>
    <time class="watch-player__date" datetime="{publishedIso}">{publishedText}</time>
  </p>
  <p class="watch-player__desc" id="watch-player-desc">{description}</p>
  <button type="button" class="watch-player__more" aria-expanded="false" aria-controls="watch-player-desc" hidden>Show more</button>
  <p class="watch-player__links">
    <a href="https://www.youtube.com/watch?v={id}&list={youtubeId}" data-testid="watch-youtube-link">Watch on YouTube</a>
    <a href="#watch-panel-{slug}" class="watch-player__back" data-testid="watch-back-link">Back to video list</a>
  </p>
</section>
```

Icon: `CirclePlay` from `lucide-astro` (present in `node_modules/lucide-astro/dist`; the package is already used by `src/components/ResponsibleAIEvidenceMark.astro:8`).

**`WatchPanel.astro`** (props: `playlist: WatchPlaylistView`, `selected: boolean`, `eagerFirstRow: boolean`)

```html
<div class="watch-panel" role="tabpanel" id="watch-panel-{slug}" aria-labelledby="watch-panel-{slug}-title" data-testid="watch-panel" data-playlist="{slug}" hidden={!selected}>
  <!-- labelled by its own h2, not the tab: the tab's name comes from a second aria-labelledby, which the name calculation does not follow, so pointing at the tab would read name, creator and description -->
  <div class="watch-panel__head">
    <h2 class="watch-panel__title" id="watch-panel-{slug}-title">{name}</h2>
    <span class="watch-panel__count" data-testid="watch-panel-count">{n} videos</span>  <!-- "1 video" -->
  </div>
  <ul class="watch-grid" data-testid="watch-grid">  <!-- status ok -->
    <li><VideoThumb video playlist eager={eagerFirstRow && index < 2} /></li>
  </ul>
  <div data-testid="watch-empty"><EmptyState message="…">…</EmptyState></div>  <!-- status empty or failed, § 5 -->
</div>
```

**`VideoThumb.astro`** (props: `video: WatchVideoView`, `playlist: WatchPlaylistView`, `eager: boolean`)

```html
<a class="watch-thumb" href="https://www.youtube.com/watch?v={id}&list={youtubeId}"
   id="watch-thumb-{slug}-{id}" aria-labelledby="watch-thumb-{slug}-{id}-title" aria-describedby="watch-thumb-{slug}-{id}-meta"
   data-testid="watch-thumb" data-video-id="{id}" data-playlist="{slug}" data-frame-tier="{sd|mq}">
  <span class="watch-thumb__media">
    <img class="watch-thumb__cover" src srcset sizes="(max-width: 640px) 100vw, (max-width: 1119px) 50vw, 540px"
         alt="" loading="lazy|eager" decoding="async" referrerpolicy="no-referrer" width="480" height="270">
    <!-- frame layers are created by JS on first preview, never in server HTML -->
    <span class="watch-thumb__duration" aria-hidden="true" data-testid="watch-thumb-duration">{durationText}</span>
  </span>
  <span class="watch-thumb__title" id="watch-thumb-{slug}-{id}-title" data-testid="watch-thumb-title">{title}</span>
  <span class="watch-thumb__playing" hidden>Playing</span>
  <span class="sr-only" id="watch-thumb-{slug}-{id}-meta">{channel}, {durationSpoken}, published {publishedText}</span>
</a>
```

The playing card gets `aria-current="true"` and its "Playing" label unhidden. The same video can sit in two playlists, so IDs include the slug.

**`VideoPopup.astro`** (props: none)

```html
<div class="watch-popup" aria-hidden="true" data-testid="watch-popup" hidden>
  <p class="watch-popup__title"></p>
  <p class="watch-popup__meta"><span class="watch-popup__channel"></span> <span class="watch-popup__duration"></span> <span class="watch-popup__date"></span></p>
  <p class="watch-popup__desc"></p>
</div>
```

`aria-hidden` because every field it shows already reaches screen readers through the card's name, its `aria-describedby` text, or the player. It holds no links and never takes focus. JS fills it and sets `data-video-id`.

**`PreviewSwitch.astro`** (props: none; rendered `hidden`, shown by JS on mouse devices)

```html
<div class="watch-switch" data-testid="watch-preview-switch" hidden>
  <span class="watch-switch__label" id="watch-switch-label">Hover previews</span>
  <div class="watch-switch__group" role="radiogroup" aria-labelledby="watch-switch-label" aria-describedby="watch-switch-hint">
    <button type="button" class="watch-switch__radio" role="radio" aria-checked="true" data-value="on">On</button>
    <button type="button" class="watch-switch__radio" role="radio" aria-checked="false" data-value="off">Off</button>
  </div>
  <p class="watch-switch__hint" id="watch-switch-hint" data-testid="watch-preview-hint" hidden>Off because reduce motion is on.</p>
</div>
```

### 3.4 Reused as is, and what changes in existing files

| Item | Path | How it is reused |
|---|---|---|
| `Base` (`layout="wide"`, 80rem) | `src/layouts/Base.astro:28-29`, `:539` | Page shell, nav, footer, A11yControl, theme |
| `Breadcrumb` | `src/components/Breadcrumb.astro` | Home / Watch |
| h1 + `.lede` | `src/pages/privacy.astro:11-15`, `:56-59` | Same markup; `.lede` is scoped there, so copy its two declarations |
| `EmptyState` | `src/components/EmptyState.astro` | Panel empty and failed states |
| `jsonForScript` | `src/lib/jsonForScript.ts` | Payload |
| `formatPostDate` | `src/lib/writing.ts:21` | Dates, at build only (the module imports `astro:content`, so never into client code) |
| Global focus ring, `.sr-only`, `[hidden]` rule | `src/styles/global.css:105-109`, `:226-233`, `:17` | All new controls |
| Tokens | `src/styles/tokens.css` | All colours, spacing, type, radius, popover, radio |
| `CirclePlay` icon | `lucide-astro` | Play button |

Reused by copying declarations (the source styles are in Astro-scoped `<style>` blocks, so another component cannot use the class names; copy the declarations with the same tokens and leave the source files untouched):

| New class | Copied from | Note |
|---|---|---|
| `.watch-switch__label`, `.watch-switch__radio` | `.a11y-label`, `.a11y-radio` and its hover, checked, focus and mobile rules, `src/components/A11yControl.astro:239-302` | Same look as the Motion setting |
| `.watch-popup` | `.ev-popup` and its fade-in, `src/components/ResponsibleAIEvidenceMark.astro:198-233` | Width `min(20rem, calc(100vw - 32px))` |
| `.watch-rail__label`, `.watch-rail__line` | `.facet-label`, `.facet-line`, `src/components/FacetBar.astro:58-72` | "Playlists" label with rule |
| `.watch-thumb__media:hover` | `.entity-card:hover`, `src/components/EntityCard.astro` | Accent border on hover |
| `.watch-player__date`, `.watch-panel__count` | `.post-date`, `src/pages/writing/index.astro` | Mono, 2xs, uppercase, faint |

Behaviour ported, not shared: the popup logic in `ResponsibleAIEvidenceMark.astro:61-158` (fine-pointer media query, `pointerover`/`pointerout` edge-crossing check, separate open and close timers, Escape, `focusout`, 16px edge clamp). That script stays unchanged: it pins on click and owns one popup per mark, while /watch plays on click and uses one shared popup. The edge clamp moves into `src/lib/watch/popup-position.ts`. The radiogroup arrow keys follow `A11yControl.astro` (arrow moves focus and selects; every radio stays in the tab order).

Generalisation required (one): `src/components/EmptyState.astro` gets a `<slot />` after its `<p>`, so the failed state can carry a link. Its seven current users (`src/pages/research/{subjects,products,sources,criteria,claims,companies}/index.astro`, `src/pages/research/topics/[topic].astro`) pass no children, so their output does not change. Add `.empty-state :global(a) { color: var(--color-accent); }` only if the inherited link colour is lost.

Optional later (not in this item): move the segmented-radio and popover declarations into `global.css` so A11yControl, the evidence marks and /watch share one copy. File in `docs/UNSCHEDULED.md` if wanted.

## 4. Interaction

### 4.1 Timings (named constants in `src/lib/watch/timings.ts`)

| Constant | Value | Use |
|---|---|---|
| `POPUP_OPEN_DELAY_MS` | 300 | Mouse rest on a card before the popup opens. Longer than the evidence marks' 150 because large adjacent cards would flash popups as the pointer crosses the grid |
| `POPUP_CLOSE_DELAY_MS` | 150 | After the pointer leaves card and popup (matches `HOVER_DELAY`, `ResponsibleAIEvidenceMark.astro:68`) |
| `POPUP_FADE_MS` | 150 | Popup fade-in (same as `ev-popup-in`) |
| `FRAME_LOAD_AT_MS` | 300 | Frames start loading (same moment the popup opens) |
| `FRAME_FIRST_AT_MS` | 600 | First frame shows at this point, or when it finishes loading if later |
| `FRAME_INTERVAL_MS` | 900 | Time per frame |
| `FRAME_FADE_MS` | 200 | Crossfade between frames; 0 when a reduce-motion setting is on |

All delays are measured from when the pointer comes to rest on the card (or keyboard focus arrives). Playwright tests advance them with `page.clock`; no test-only hooks in page code.

### 4.2 Card states

| Input | Detected by | Popup | Frames | Activate |
|---|---|---|---|---|
| Mouse | `(hover: hover) and (pointer: fine)` and `pointerType === 'mouse'` (same check as `ResponsibleAIEvidenceMark.astro:69`, `:126`) | After 300ms rest; once a popup is open, moving to another card swaps at once | If previews are on (§ 4.5) | Click plays in page. Ctrl, Cmd, Shift, Alt or middle click: default link behaviour (opens YouTube) |
| Keyboard | Focus with `:focus-visible` matching | At once on focus | If previews are on and the device has a mouse; same delays from focus | Enter plays |
| Touch, pen | Anything else | Never | Never | Tap plays |
| Screen reader | | Not exposed (`aria-hidden`) | Not exposed | Card name is the title; description is "Channel, 22 minutes 58 seconds, published November 3, 2025" |

Visual states of `.watch-thumb`: rest; hover and focus (accent border on `.watch-thumb__media`, title underlined); previewing (`data-previewing="true"`, frame layer shown); playing (`aria-current="true"`, 2px accent border, "Playing" label).

### 4.3 Popup

- Content: title (Georgia), channel, duration and date (mono), description clamped to 4 lines. No links.
- One shared element, `position: fixed`, moved between cards. Anchor is the whole card (`.watch-thumb`).
- Placement, computed by `placePopup()`:
  1. Right of the card, top aligned with the card top, touching it (no gap), if `width + 16px` fits to the right.
  2. Else left of the card, same rules.
  3. Else directly below the card.
  4. Clamp horizontally to 16px from the viewport edges.
  5. Clamp the top to at least `max(16px, playerFrame.bottom)` (the player box's bottom edge in the viewport) so the popup never covers the player. Clamp the bottom to `innerHeight - 16px` only while that does not break rule 5.
  6. If the result still intersects the player box, do not open.
- Never "above": a first-row card's popup would land on the player.
- Close on: pointer outside card and popup for 150ms; Escape (focus stays where it is); focus leaving the card; any scroll (window, capture phase); resize; click; playlist change; `visibilitychange` to hidden.
- Pointer moving from card into popup keeps it open: treat the popup as part of its card's hover zone.
- Fade-in 150ms, removed under `prefers-reduced-motion: reduce` or `html[data-motion="reduce"]`.

### 4.4 Frame cycling

- Frame list: `https://i.ytimg.com/vi/{id}/{tier}1.jpg`, `{tier}2.jpg`, `{tier}3.jpg`, where `tier` is the card's `data-frame-tier` (`sd` or `mq`). Order 1, 2, 3, 1, 2, 3 while hovered or focused. The cover is not part of the loop.
- Loading: nothing on page load. At 300ms rest, create three `Image()` objects with `referrerPolicy = 'no-referrer'`. Cache them per video so a second hover starts at once.
- A missing frame returns HTTP 404 with a 120x90 grey JPEG, which may not fire `onerror` (both research docs). Treat a frame as failed if `onerror` fires or `naturalWidth <= 120`. Skip failed frames; if all fail, no preview for that card.
- Display: two `<img class="watch-thumb__frame" alt="" aria-hidden="true">` layers inserted into `.watch-thumb__media` on first preview, alternating, `object-fit: cover` (crops the `sd` letterbox bars), opacity crossfade of `FRAME_FADE_MS`.
- Stop and restore the cover at once (no fade) on: pointer leave, focus leave, Escape, click, playlist change, tab hidden, switch turned off.
- State hooks for tests: while cycling, the card has `data-previewing="true"` and `data-frame="1|2|3"`.

### 4.5 Hover previews switch

- Shown only when `(hover: hover) and (pointer: fine)` matches; follows changes to that media query.
- Effective state, from a pure function `previewsEnabled(stored, osReduce, siteReduce)` in `src/lib/watch/preview.ts`:

| Stored `dr-watch-previews` | OS reduce or `html[data-motion="reduce"]` | Result | Hint shown |
|---|---|---|---|
| `on` | any | On | No |
| `off` | any | Off | No |
| none | yes | Off | Yes: "Off because reduce motion is on." |
| none | no | On | No |

- `siteReduce` reads `html[data-motion]`, which `A11yControl.astro:506-510` sets from both the OS setting and `dr-motion`; still check the media query directly in case A11yControl has not run.
- With no stored value, recompute live: listen to `matchMedia('(prefers-reduced-motion: reduce)')` changes and watch `data-motion` with a `MutationObserver` (A11yControl changes it without a reload).
- Pressing On or Off writes `dr-watch-previews` (read and write inside try/catch, as `A11yControl.astro` `read`/`write`). Arrow keys move and select, as in A11yControl. Turning Off stops any running cycle at once.
- On while a reduce setting is on: frames swap without the crossfade.

### 4.6 Playlist selection (tabs)

- Manual activation: arrows move focus only; Enter or Space selects. Up and Left go to the previous tab, Down and Right to the next, wrapping; Home and End go to the first and last. Roving `tabindex` (selected tab `0`, others `-1`, focus moves the `0`).
- Selecting: set `aria-selected`, unhide its panel and hide the others, close any popup, stop frames, announce (§ 4.9), update the URL (§ 4.8). Focus stays on the tab.
- If nothing has played yet, the player poster follows the new playlist's first video. If a video has been loaded, the player keeps it (and keeps playing); only the grid changes.
- Selected tab style: 3px accent left border, `--color-text-heading`, name weight 600. Not colour alone.

### 4.7 Video selection and player

| Event | Result |
|---|---|
| Page load | Poster of the selected video (deep link) or the first video of the selected playlist. No iframe. No request to `youtube-nocookie.com` |
| Press Play on the poster | Replace the poster button with the iframe (`autoplay=1`, the click is the user gesture). Focus moves to the player title |
| Click a card | Put that video in the player (title, meta, description, links; poster image swapped), remove any existing iframe (one iframe at a time), mark the card playing, focus the title with `preventScroll: true`. Then: if `watch-player-frame` is at least 50% in view, insert the new iframe with `autoplay=1` at once. Otherwise scroll it into view (`smooth`, or `auto` under a reduce setting) and insert the iframe only when an `IntersectionObserver` on the frame reports 50% or more visible (YouTube rule: no autoplay until the player is visible and more than half on screen) |
| Video ends | YouTube's own end screen. No play-next, no IFrame Player API script; `rel=0` limits suggestions to the same channel |
| Show more | Shown only when the description overflows 3 lines; toggles `aria-expanded` and the clamp; label switches "Show more" / "Show less" |
| Back to video list | Focus the playing card (`preventScroll: false`); without a playing card, the first card of the selected panel |
| Watch on YouTube | Normal link, always present |

The description is plain text with `white-space: pre-line`; no auto-linking.

### 4.8 URL sync

- Shape: `/watch?list={slug}&v={videoId}`. Query, not hash (the skip link uses `#main-content`, `src/layouts/Base.astro:142`).
- Write with `history.replaceState` only (no history entries per pick).
- Before any video is loaded: `list` follows the selected tab, `v` omitted. After one is loaded: `list` and `v` name the loaded video and its playlist; changing tabs afterwards does not change the URL.
- Arrival: `list` known selects that tab. `v` known in that playlist sets the poster (no iframe) and counts as loaded, so the URL keeps it. `v` given without `list`: use the first playlist containing it. Unknown `list`: first default playlist, URL rewritten without it. Unknown `v`: first video of the playlist, show the notice "That video is no longer in this playlist.", URL rewritten without `v`.
- Parsing and serialising live in `src/lib/watch/state.ts` (covered by the arch doc's URL round-trip unit test, U8).

### 4.9 Live region

One `role="status"` `aria-live="polite"` `.sr-only` paragraph in the page (pattern from `src/components/PetitionSign.astro:74`).

| Event | Announcement |
|---|---|
| Playlist selected, has videos | "{Playlist name}, {n} videos." ("1 video") |
| Playlist selected, empty or failed | "{Playlist name}, no videos to show." |
| Video picked | None (focus moves to the title, which is read) |
| Switch changed | None (the radio's checked state is read) |

### 4.10 Without JavaScript

The `<noscript><style>` block in the page sets `.watch-panel[hidden] { display: block !important; }` (beats the global `[hidden]` rule, `global.css:17`, by specificity) and hides `.watch-tabs`, `.watch-player`, `.watch-switch`. Readers see every playlist's heading and grid; each card links to `youtube.com/watch`. No popups, previews or embed.

## 5. Empty and error states

| Case | Where | Copy |
|---|---|---|
| A playlist's videos could not be fetched this build (its title is known) | Its panel, `EmptyState` with slot | "These videos could not be loaded." + link "See the playlist on YouTube" (`https://www.youtube.com/playlist?list={youtubeId}`) |
| No data at all (no key, or a global API error) | Page-level empty state (`watch-page-empty`); no tabs, player, switch or panels (plan P8) | "These videos could not be loaded." |
| Playlist has no public videos | Its panel | "This playlist has no public videos right now." |
| Selected playlist empty, nothing played | Player stays on the previous poster, or `hidden` if none was ever set | n/a |
| Unknown `v` in the URL | Above the player frame | "That video is no longer in this playlist." |
| Video removed or blocked after the build | Inside the iframe (YouTube's message) | "Watch on YouTube" stays under the player |
| Cover image missing | Card | `.watch-thumb__media` shows `--color-surface`; title stays visible below. Test how the 404 grey image renders before adding anything more |
| No JavaScript | Whole page | § 4.10; no extra copy |

Keyless local builds show the page-level empty state; the build log carries the reason (arch doc § 1, `WATCH_DATA`).

## 6. Privacy page draft (for Brandon's review)

Draft, Brandon to review. Replaces the paragraph under "Reading the site" in `src/pages/privacy.astro:18-20` and adds one section.

> The site runs no analytics or tracking scripts. Display settings, such as theme and text size, are saved only in your browser. One exception: the Watch page.
>
> **Watching videos** (`<h2 id="watch">`)
>
> The Watch page (`/watch`) lists videos from YouTube. Its thumbnails and hover previews load from YouTube's image servers, so YouTube (Google) receives your IP address when you open the page or hover over a video. The video player loads only when you press Play or pick a video. It comes from youtube-nocookie.com, and once it loads, YouTube's own policies apply, including anything it stores in your browser. Your hover previews setting is saved only in your browser.
>
> The video list comes from YouTube API Services. See the [Google Privacy Policy](https://policies.google.com/privacy) and the [YouTube Terms of Service](https://www.youtube.com/t/terms).

Also stale once /watch ships: the comment at `src/layouts/Base.astro:2` ("pages make no third-party requests") needs "except /watch".

## 7. CSS

### 7.1 Tokens used (all in `src/styles/tokens.css`)

| Purpose | Tokens |
|---|---|
| Text | `--color-text`, `--color-text-heading`, `--color-text-muted`, `--color-text-faint`, `--color-section-label` |
| Surfaces, lines, accent | `--color-bg`, `--color-surface`, `--color-border`, `--color-accent` |
| Popup | `--color-popover-bg`, `--color-popover-border`, `--shadow-popover`, `--radius-md` |
| Switch, tab hover | `--color-radio-selected-bg`, `--color-radio-selected-border`, `--color-radio-text`, `--color-radio-text-selected` |
| Type | `--font-heading` (titles), `--font-display` (h1 via global), `--font-body`, `--font-mono` (duration, dates, counts), `--font-size-sm`, `--font-size-xs`, `--font-size-2xs`, `--line-height-heading` |
| Space, radius | `--space-xs` to `--space-2xl`, `--radius-sm`, `--radius-md`, `--radius-full` |

No new tokens. Fixed colours appear only on elements that sit on video imagery, identical in every theme: player box `#000`; duration badge and Play pill `#fff` on `rgba(0, 0, 0, 0.8)`. Under `[data-contrast="high"]` the badge and pill add `border: 1px solid #fff`.

### 7.2 Classes

| Class | Key rules |
|---|---|
| `.watch-layout` | `display: grid; grid-template-columns: 15rem minmax(0, 1fr); gap: var(--space-xl)`; one column below 1120px |
| `.watch-rail` | `position: sticky; top: var(--space-lg); align-self: start; max-height: calc(100vh - 2 * var(--space-lg)); overflow-y: auto`; static below 1120px, `margin-bottom: var(--space-lg)` |
| `.watch-tab` | Full-width button, left aligned, `padding: var(--space-sm) var(--space-md)`, `border: 0; border-left: 3px solid transparent`, transparent background, `min-height: 44px`; hover `--color-radio-selected-bg`; `[aria-selected="true"]` accent left border |
| `.watch-tab__name` | `--font-heading`, 1.05rem, `--color-text-muted`; selected: `--color-text-heading`, 600 |
| `.watch-tab__creator` | `--font-size-xs`, `--color-text-faint` |
| `.watch-tab__desc` | `--font-size-xs`, `--color-text-muted`, 3-line clamp; 2 lines below 1120px |
| `.watch-player__frame` | `aspect-ratio: 16 / 9; width: min(100%, calc(70vh * 16 / 9)); min-height: 200px; background: #000; border-radius: var(--radius-md); overflow: hidden; position: relative` |
| `.watch-player__poster`, `__img`, `__iframe` | Fill the frame; `object-fit: cover` on the image; poster button no border or padding |
| `.watch-player__play` | Centred pill, `--radius-full`, `rgba(0,0,0,0.8)`, `#fff`, `--font-size-sm`, 600; poster hover darkens to `0.9` |
| `.watch-player__title` | h2, 1.25rem, `margin: var(--space-md) 0 var(--space-xs)` |
| `.watch-player__meta` | Flex, wrap, `gap: var(--space-md)`; channel `--font-size-sm` muted; duration and date as `.post-date` |
| `.watch-player__desc` | `--font-size-sm`, muted, `white-space: pre-line`, 3-line clamp unless `[data-expanded]` |
| `.watch-player__more` | Text button in accent, no border, `--font-size-sm` |
| `.watch-player__links` | Flex, `gap: var(--space-lg)` |
| `.watch-notice` | `--font-size-sm`, muted, `margin-bottom: var(--space-sm)` |
| `.watch-toolbar` | Flex, `justify-content: space-between; align-items: end; flex-wrap: wrap; gap: var(--space-md)`, `margin-top: var(--space-xl); padding-top: var(--space-lg); border-top: 1px solid var(--color-border)` |
| `.watch-attribution` | `--font-size-xs`, `--color-text-faint` |
| `.watch-switch`, `__label`, `__group`, `__radio` | Copies of `.a11y-label`, `.a11y-group`, `.a11y-radio` (§ 3.4); radios `padding: 0 0.75rem`, not `flex: 1` |
| `.watch-switch__hint` | `--font-size-2xs`, faint |
| `.watch-panel__head` | Flex, baseline, `gap: var(--space-md)`, `margin: var(--space-lg) 0 var(--space-md)` |
| `.watch-panel__title` | h2 at 1.2rem |
| `.watch-grid` | List reset; `display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-xl) var(--space-lg)`; 1 column at 640px and down |
| `.watch-thumb` | `display: block; color: inherit; text-decoration: none` |
| `.watch-thumb__media` | `position: relative; display: block; aspect-ratio: 16 / 9; overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); transition: border-color 0.15s` |
| `.watch-thumb:hover .watch-thumb__media`, `.watch-thumb:focus-visible .watch-thumb__media` | `border-color: var(--color-accent)` |
| `.watch-thumb[aria-current="true"] .watch-thumb__media` | `border-color: var(--color-accent); box-shadow: 0 0 0 1px var(--color-accent)` |
| `.watch-thumb__cover`, `.watch-thumb__frame` | `position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover`; frame `opacity: 0`, `.is-shown` `opacity: 1`, `transition: opacity 0.2s` |
| `.watch-thumb__duration` | Bottom right `0.4rem`, `--font-mono`, `--font-size-2xs`, `padding: 0 0.35em`, `--radius-sm`, fixed colours § 7.1 |
| `.watch-thumb__title` | `display: block; margin-top: var(--space-sm)`; `--font-heading`, 1rem, `--color-text`, 2-line clamp; underlined on card hover |
| `.watch-thumb__playing` | As `.post-date` but `color: var(--color-accent)` |
| `.watch-popup` | Copy of `.ev-popup` (§ 3.4) with `position: fixed`, `width: min(20rem, calc(100vw - 32px))` |
| `.watch-popup__title` | `--font-heading`, `--font-size-sm`, `--color-text`, `margin: 0 0 var(--space-xs)` |
| `.watch-popup__meta` | Muted; duration and date in `--font-mono` |
| `.watch-popup__desc` | 4-line clamp, `margin: var(--space-xs) 0 0` |

### 7.3 Themes, motion, focus

- Themes: every themed colour is a token; `tokens.css` switches them on `[data-theme]` and `[data-contrast]`, set before paint by `Base.astro:109-131`. Nothing on /watch reads the theme. Check all four combinations (dark, light, dark high contrast, light high contrast).
- Motion: remove all transitions and animations (card border, frame crossfade, popup fade, smooth scroll) under both `@media (prefers-reduced-motion: reduce)` and `:root[data-motion="reduce"]`, as `global.css:44-49` and `A11yControl.astro` style block do.
- Focus: global `:focus-visible` (`global.css:105-109`: 2px accent, 3px offset) on tabs, cards (ring wraps image and title), poster button, links, Show more. Switch radios use the copied `.a11y-radio:focus-visible` (1px offset). The player title (`tabindex="-1"`) gets the ring only after keyboard use (browser `:focus-visible` rule).
- Targets: tabs 44px tall; switch radios 36px (44px at 640px and down, as `.a11y-radio`).

### 7.4 Images

- Cover: `srcset` from `cover`, `sizes="(max-width: 640px) 100vw, (max-width: 1119px) 50vw, 540px"`, `width`/`height` set to avoid layout shift, `decoding="async"`, `referrerpolicy="no-referrer"`.
- `loading="eager"` only on the poster and the first 2 cards of the server-default playlist; everything else `lazy`. Hidden panels' lazy images do not load until their tab is shown (arch doc § 5; confirm in the Network panel).
- Never `referrerpolicy` on the iframe.

## 8. Test hooks (Playwright)

Prefer role and name; use `data-testid` where the name is not stable or there is no role. Scope every query to `[data-testid="watch-page"]`: Base renders another `role="status"` (`Base.astro:136`).

| Element | Selector |
|---|---|
| Page root | `[data-testid="watch-page"]` |
| Intro stub | `[data-testid="watch-lede"]` |
| Playlist list | `getByRole('tablist', { name: 'Playlists' })` |
| Playlist tab | `getByRole('tab', { name: '<playlist name>', exact: true })`; `[data-testid="watch-tab"][data-playlist="<slug>"]` |
| Panel | `getByRole('tabpanel', { name: '<playlist name>', exact: true })`; `[data-testid="watch-panel"][data-playlist="<slug>"]` |
| Panel count | `[data-testid="watch-panel-count"]` |
| Grid | `[data-testid="watch-grid"]` |
| Card | `[data-testid="watch-thumb"][data-video-id="<id>"]`; `getByRole('link', { name: '<title>' })` |
| Card title | `[data-testid="watch-thumb-title"]` |
| Duration badge | `[data-testid="watch-thumb-duration"]` |
| Card preview state | Card attributes `data-previewing`, `data-frame`; layers `img.watch-thumb__frame` |
| Playing card | `[data-testid="watch-thumb"][aria-current="true"]` |
| Popup | `[data-testid="watch-popup"]` (visible = not `hidden`), its `data-video-id` |
| Player | `[data-testid="watch-player"]` (`data-video-id`, `data-playlist`); `getByRole('region', { name: '<title>' })` |
| Player box | `[data-testid="watch-player-frame"]` (for overlap and size checks) |
| Play button | `getByRole('button', { name: /^Play: / })`; `[data-testid="watch-play"]` |
| Iframe | `[data-testid="watch-iframe"]` (assert `src` host `www.youtube-nocookie.com`) |
| Player title, meta | `[data-testid="watch-player-title"]`, `[data-testid="watch-player-meta"]` |
| Show more | `getByRole('button', { name: 'Show more' })` |
| Watch on YouTube | `getByRole('link', { name: 'Watch on YouTube' })` |
| Back to list | `getByRole('link', { name: 'Back to video list' })` |
| Deep-link notice | `[data-testid="watch-notice"]` |
| Switch | `getByRole('radiogroup', { name: 'Hover previews' })`, then `getByRole('radio', { name: 'On' })` / `'Off'`; container `[data-testid="watch-preview-switch"]` |
| Switch hint | `[data-testid="watch-preview-hint"]` |
| Live region | `[data-testid="watch-status"]` |
| Empty state | `[data-testid="watch-empty"]` |
| Terms link | `getByRole('link', { name: 'YouTube Terms of Service' })` |

Test setup notes:
- Build with `WATCH_DATA=fixture` (synthetic data, arch doc § 1).
- Route `https://i.ytimg.com/**` to local fixture JPEGs (one route returning a 120x90 image with status 404, to cover failed frames) and `https://www.youtube-nocookie.com/**` to a blank page, so tests run offline and request counts are exact.
- Use `page.clock` to step through § 4.1 timings; `page.emulateMedia({ reducedMotion: 'reduce' })`; set `dr-motion` or `dr-watch-previews` with `addInitScript`; touch with a `hasTouch` / `isMobile` context; no-JS with `javaScriptEnabled: false`.
- Scenarios: the arch doc's browser scenarios E1 to E9 (playlist switch, deep link, frame cycling, switch persistence, reduce motion, keyboard, network before click, popup never over the player using the player box hook, player minimum size), plus: a card clicked far down the grid inserts no `watch-iframe` until the player box is at least half visible; tab keyboard (arrows, Home, End, manual activation); unknown `v` shows the notice; failed-frame skip; no-JS shows all panels with YouTube links; popup closes on Escape without moving focus; switch hidden on touch; four theme combinations render (screenshot per combination).

## 9. Open items for Brandon

| ID | Item |
|---|---|
| Q-UI1 | Intro copy: replace `WATCH_LEDE` ("Intro: TBD, Brandon to write.") and pass the same text as the page `description`. The stub ships visibly if not replaced |
| Q-UI2 | Privacy draft in § 6 |
| Q-UI3 | Playlist descriptions (YAML `description`, 200 chars max) for the three seed playlists; without them the API description is cut to 200 chars |
| Q-UI4 | Resolved: the "Dangerous Robot" playlist is public, so `creator` comes from the API unless the YAML sets it |

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-12 | agent (claude-opus-5-5), fresh-eyes review | This spec end to end with `watch-page.md` | Fixed stale slug, private-playlist and keyless empty-state text |

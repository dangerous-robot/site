// Player behaviour (UI spec § 4.7). Renders every watch:video into the
// server-rendered player: play: false swaps the poster and shows the notice
// only when notice is true; play: true also inserts the embed once the frame
// is at least half in view. Emits watch:play when the embed goes in.
import {
  ATTR,
  CLASS,
  EMBED_ALLOW,
  PLAYER_MIN_VISIBLE_RATIO,
  TESTID,
  embedTitle,
  embedUrl,
  emitWatch,
  onWatch,
  youtubeWatchUrl,
} from '../../../lib/watch/contract';
import { coverSrcset } from '../../../lib/watch/images';
import { indexPlaylists, type VideoEntry } from '../../../lib/watch/index';
import type { WatchPlaylistView } from '../../../lib/watch/types';
import { byTestId, setText } from './dom';

type Entry = VideoEntry<WatchPlaylistView>;

/** Share of the element's area inside the viewport, as IntersectionObserver measures it. */
function visibleRatio(el: Element): number {
  const r = el.getBoundingClientRect();
  const area = r.width * r.height;
  if (area === 0) return 0;
  const w = Math.max(0, Math.min(r.right, window.innerWidth) - Math.max(r.left, 0));
  const h = Math.max(0, Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0));
  return (w * h) / area;
}

export function initPlayer(root: HTMLElement, bus: EventTarget, data: WatchPlaylistView[]): void {
  const player = byTestId(root, TESTID.player);
  const frame = player && byTestId(player, TESTID.playerFrame);
  const poster = player && byTestId<HTMLButtonElement>(player, TESTID.play);
  const title = player && byTestId(player, TESTID.playerTitle);
  if (!player || !frame || !poster || !title) return;

  // The notice sits just outside the player, so it can show while the player is hidden.
  const notice = byTestId(root, TESTID.notice);
  const img = poster.querySelector<HTMLImageElement>('.watch-player__img');
  const channel = player.querySelector<HTMLElement>('.watch-player__channel');
  const duration = player.querySelector<HTMLElement>('.watch-player__duration');
  const date = player.querySelector<HTMLTimeElement>('.watch-player__date');
  const desc = player.querySelector<HTMLElement>('.watch-player__desc');
  const more = player.querySelector<HTMLButtonElement>('.watch-player__more');
  const youtubeLink = byTestId<HTMLAnchorElement>(player, TESTID.youtubeLink);
  const from = byTestId(player, TESTID.playerFrom);
  const index = indexPlaylists(data);

  // What the player shows, starting with what the server rendered.
  let current: Entry | null = index.findVideo(player.getAttribute(ATTR.playlist) ?? '', player.getAttribute(ATTR.videoId) ?? '');
  let embed: HTMLIFrameElement | null = null;
  // A pick made while an earlier one waits for the frame to scroll into view
  // must cancel it, or the earlier video's embed would appear late.
  let pending: IntersectionObserver | null = null;

  const cancelPending = () => {
    pending?.disconnect();
    pending = null;
  };

  const removeEmbed = () => {
    embed?.remove();
    embed = null;
    poster.hidden = false;
  };

  // Clamp the description to two lines and offer Show more only when it
  // overflows. Measured, not counted: line count depends on text and width.
  const capDescription = () => {
    if (!desc || !more) return;
    const expanded = more.getAttribute('aria-expanded') === 'true';
    delete desc.dataset.expanded;
    const overflows = desc.scrollHeight > desc.clientHeight + 1;
    if (overflows && expanded) desc.dataset.expanded = '';
    more.hidden = !overflows;
    if (!overflows) more.setAttribute('aria-expanded', 'false');
    more.textContent = overflows && expanded ? 'Show less' : 'Show more';
  };

  const render = ({ playlist, video }: Entry) => {
    player.setAttribute(ATTR.videoId, video.id);
    player.setAttribute(ATTR.playlist, playlist.slug);
    poster.setAttribute('aria-label', `Play: ${video.title}`);
    if (img) {
      // A stale srcset would win over the new src.
      const srcset = coverSrcset(video.cover);
      if (srcset) img.srcset = srcset;
      else img.removeAttribute('srcset');
      img.src = video.cover.src;
    }
    // Never hidden: the title is where focus goes on every pick.
    title.textContent = video.title;
    setText(channel, video.channel);
    setText(duration, video.durationText);
    if (date) date.dateTime = video.publishedIso;
    setText(date, video.publishedText);
    setText(desc, video.description);
    more?.setAttribute('aria-expanded', 'false');
    capDescription();
    if (from) from.textContent = playlist.name;
    if (youtubeLink) youtubeLink.href = youtubeWatchUrl(video.id, playlist.youtubeId);
  };

  const insertEmbed = ({ playlist, video }: Entry) => {
    const iframe = document.createElement('iframe');
    iframe.className = CLASS.playerIframe;
    iframe.setAttribute('data-testid', TESTID.iframe);
    iframe.title = embedTitle(video.title);
    iframe.setAttribute('allow', EMBED_ALLOW);
    iframe.setAttribute('allowfullscreen', '');
    // No referrerpolicy attribute: YouTube answers a missing referrer with Error 153.
    iframe.src = embedUrl(video.id);
    const hadFocus = poster.contains(document.activeElement);
    poster.hidden = true;
    frame.append(iframe);
    embed = iframe;
    // Hiding the focused poster drops focus to the body.
    if (hadFocus) title.focus({ preventScroll: true });
    if (notice) notice.hidden = true;
    emitWatch(bus, 'watch:play', { slug: playlist.slug, id: video.id });
  };

  // No behavior option: the site's scroll-behavior (global.css) is smooth,
  // and auto under either reduce setting.
  const scrollToFrame = () => frame.scrollIntoView({ block: 'center' });

  // YouTube rule: no autoplay until the player is more than half on screen.
  // The synchronous check lets a pick with the player in view start at once;
  // the observer's first report would only arrive a frame later.
  const play = (entry: Entry) => {
    title.focus({ preventScroll: true });
    if (visibleRatio(frame) >= PLAYER_MIN_VISIBLE_RATIO) {
      insertEmbed(entry);
      return;
    }
    scrollToFrame();
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting && e.intersectionRatio >= PLAYER_MIN_VISIBLE_RATIO)) {
          cancelPending();
          insertEmbed(entry);
        }
      },
      // 1 as well: if the crossing report lands a hair under the ratio, the
      // frame still settles fully in view and reports again.
      { threshold: [PLAYER_MIN_VISIBLE_RATIO, 1] },
    );
    pending = observer;
    observer.observe(frame);
  };

  onWatch(bus, 'watch:video', ({ slug, id, play: start, notice: showNotice }) => {
    const entry = index.findVideo(slug, id);
    if (!entry) return;
    cancelPending();
    player.hidden = false;
    if (notice) notice.hidden = !showNotice;
    const same = entry.playlist === current?.playlist && entry.video === current.video;
    if (same && embed) {
      // Picking the video that is already playing would restart it; only
      // bring the player back to the reader.
      if (start) {
        title.focus({ preventScroll: true });
        if (visibleRatio(frame) < PLAYER_MIN_VISIBLE_RATIO) scrollToFrame();
      }
      return;
    }
    removeEmbed();
    // The server already rendered its default video; re-rendering it would
    // only force a layout to measure the description.
    if (!same) render(entry);
    current = entry;
    if (start) play(entry);
  });

  poster.addEventListener('click', () => {
    if (!current) return;
    cancelPending();
    play(current);
  });

  more?.addEventListener('click', () => {
    more.setAttribute('aria-expanded', String(more.getAttribute('aria-expanded') !== 'true'));
    capDescription();
  });

  // Re-measure when the width changes (rotation, text size) and once web
  // fonts settle. Width only: the clamp itself changes the height.
  if (desc) {
    let width = -1;
    new ResizeObserver(([entry]) => {
      if (entry.contentRect.width === width) return;
      width = entry.contentRect.width;
      capDescription();
    }).observe(desc);
    document.fonts?.ready.then(capDescription);
  }
}

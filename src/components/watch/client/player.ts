// Player behaviour (UI spec § 4.7). Renders every watch:video into the
// server-rendered player: play: false swaps the poster and shows the notice
// only when notice is true; play: true also inserts the embed once the frame
// is at least half in view. Emits watch:play when the embed goes in.
//
// The embed is built with createElement on purpose: the post-build check
// fails if the iframe tag text appears anywhere in the built /watch HTML,
// and a small client bundle may be inlined into it.
import {
  ATTR,
  CLASS,
  EMBED_ALLOW,
  MQ_REDUCED_MOTION,
  PLAYER_MIN_VISIBLE_RATIO,
  TESTID,
  embedTitle,
  embedUrl,
  emitWatch,
  onWatch,
  youtubeWatchUrl,
} from '../../../lib/watch/contract';
import { coverSrcset } from '../../../lib/watch/frames';
import type { WatchPlaylistView, WatchVideoView } from '../../../lib/watch/types';

function byTestId<T extends Element>(scope: ParentNode, id: string): T | null {
  return scope.querySelector<T>(`[data-testid="${id}"]`);
}

/** Share of the element's area inside the viewport, as IntersectionObserver measures it. */
function visibleRatio(el: Element): number {
  const r = el.getBoundingClientRect();
  const area = r.width * r.height;
  if (area === 0) return 0;
  const w = Math.max(0, Math.min(r.right, window.innerWidth) - Math.max(r.left, 0));
  const h = Math.max(0, Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0));
  return (w * h) / area;
}

function reduceMotion(): boolean {
  return matchMedia(MQ_REDUCED_MOTION).matches || document.documentElement.dataset.motion === 'reduce';
}

export function initPlayer(root: HTMLElement, bus: EventTarget, data: WatchPlaylistView[]): void {
  const player = byTestId<HTMLElement>(root, TESTID.player);
  const frame = player && byTestId<HTMLElement>(player, TESTID.playerFrame);
  const poster = player && byTestId<HTMLButtonElement>(player, TESTID.play);
  const title = player && byTestId<HTMLElement>(player, TESTID.playerTitle);
  if (!player || !frame || !poster || !title) return;

  const notice = byTestId<HTMLElement>(player, TESTID.notice);
  const img = poster.querySelector<HTMLImageElement>('.watch-player__img');
  const channel = player.querySelector<HTMLElement>('.watch-player__channel');
  const duration = player.querySelector<HTMLElement>('.watch-player__duration');
  const date = player.querySelector<HTMLTimeElement>('.watch-player__date');
  const desc = player.querySelector<HTMLElement>('.watch-player__desc');
  const more = player.querySelector<HTMLButtonElement>('.watch-player__more');
  const youtubeLink = byTestId<HTMLAnchorElement>(player, TESTID.youtubeLink);
  const backLink = byTestId<HTMLAnchorElement>(player, TESTID.backLink);

  const playlists = new Map(data.map((p) => [p.slug, p]));
  function lookup(slug: string, id: string): { playlist: WatchPlaylistView; video: WatchVideoView } | null {
    const playlist = playlists.get(slug);
    const video = playlist?.videos.find((v) => v.id === id);
    return playlist && video ? { playlist, video } : null;
  }

  // A pick made while an earlier one waits for the frame to scroll into view
  // must cancel it, or the earlier video's embed would appear late.
  let pending: IntersectionObserver | null = null;
  function cancelPending(): void {
    pending?.disconnect();
    pending = null;
  }

  function removeEmbed(): void {
    frame!.querySelectorAll(`.${CLASS.playerIframe}`).forEach((el) => el.remove());
    poster!.hidden = false;
  }

  // Clamp the description to three lines and offer Show more only when it
  // overflows. Measured, not counted: line count depends on text and width.
  function capDescription(): void {
    if (!desc || !more) return;
    const expanded = more.getAttribute('aria-expanded') === 'true';
    delete desc.dataset.expanded;
    const overflows = desc.scrollHeight > desc.clientHeight + 1;
    if (overflows && expanded) desc.dataset.expanded = '';
    more.hidden = !overflows;
    if (!overflows) more.setAttribute('aria-expanded', 'false');
    more.textContent = overflows && expanded ? 'Show less' : 'Show more';
  }

  function render(playlist: WatchPlaylistView, video: WatchVideoView): void {
    player!.hidden = false;
    player!.setAttribute(ATTR.videoId, video.id);
    player!.setAttribute(ATTR.playlist, playlist.slug);
    poster!.setAttribute('aria-label', `Play: ${video.title}`);
    if (img) {
      // A stale srcset would win over the new src.
      const srcset = coverSrcset(video.cover);
      if (srcset) img.srcset = srcset;
      else img.removeAttribute('srcset');
      img.src = video.cover.src;
    }
    title!.textContent = video.title;
    if (channel) channel.textContent = video.channel;
    if (duration) {
      duration.textContent = video.durationText;
      // An empty span would still take a flex gap.
      duration.hidden = video.durationText === '';
    }
    if (date) {
      date.dateTime = video.publishedIso;
      date.textContent = video.publishedText;
    }
    if (desc) desc.textContent = video.description;
    if (more) more.setAttribute('aria-expanded', 'false');
    capDescription();
    if (youtubeLink) youtubeLink.href = youtubeWatchUrl(video.id, playlist.youtubeId);
    if (backLink) backLink.href = `#watch-panel-${playlist.slug}`;
  }

  function insertEmbed(playlist: WatchPlaylistView, video: WatchVideoView): void {
    cancelPending();
    removeEmbed();
    const iframe = document.createElement('iframe');
    iframe.className = CLASS.playerIframe;
    iframe.setAttribute('data-testid', TESTID.iframe);
    iframe.title = embedTitle(video.title);
    iframe.setAttribute('allow', EMBED_ALLOW);
    iframe.setAttribute('allowfullscreen', '');
    // No referrerpolicy attribute: YouTube answers a missing referrer with Error 153.
    iframe.src = embedUrl(video.id);
    const hadFocus = poster!.contains(document.activeElement);
    poster!.hidden = true;
    frame!.append(iframe);
    // Hiding the focused poster drops focus to the body.
    if (hadFocus) title!.focus({ preventScroll: true });
    if (notice) notice.hidden = true;
    emitWatch(bus, 'watch:play', { slug: playlist.slug, id: video.id });
  }

  // YouTube rule: no autoplay until the player is more than half on screen.
  // The synchronous check lets a pick with the player in view start at once;
  // the observer's first report would only arrive a frame later.
  function insertWhenVisible(playlist: WatchPlaylistView, video: WatchVideoView): void {
    cancelPending();
    if (visibleRatio(frame!) >= PLAYER_MIN_VISIBLE_RATIO) {
      insertEmbed(playlist, video);
      return;
    }
    frame!.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'center' });
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting && e.intersectionRatio >= PLAYER_MIN_VISIBLE_RATIO)) {
          insertEmbed(playlist, video);
        }
      },
      // 1 as well: if the crossing report lands a hair under the ratio, the
      // frame still settles fully in view and reports again.
      { threshold: [PLAYER_MIN_VISIBLE_RATIO, 1] },
    );
    pending = observer;
    observer.observe(frame!);
  }

  onWatch(bus, 'watch:video', ({ slug, id, play, notice: showNotice }) => {
    const found = lookup(slug, id);
    if (!found) return;
    cancelPending();
    removeEmbed();
    render(found.playlist, found.video);
    if (notice) notice.hidden = !showNotice;
    if (play) {
      title.focus({ preventScroll: true });
      insertWhenVisible(found.playlist, found.video);
    }
  });

  poster.addEventListener('click', () => {
    const found = lookup(player.getAttribute(ATTR.playlist) ?? '', player.getAttribute(ATTR.videoId) ?? '');
    if (!found) return;
    title.focus({ preventScroll: true });
    insertWhenVisible(found.playlist, found.video);
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

  // Cards in a hidden panel cannot take focus, so look only in the panel shown.
  backLink?.addEventListener('click', (event) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const panel = root.querySelector<HTMLElement>(`[data-testid="${TESTID.panel}"]:not([hidden])`);
    const card =
      panel?.querySelector<HTMLElement>(`[data-testid="${TESTID.thumb}"][aria-current="true"]`) ??
      panel?.querySelector<HTMLElement>(`[data-testid="${TESTID.thumb}"]`);
    if (!card) return;
    event.preventDefault();
    card.focus({ preventScroll: false });
  });
}

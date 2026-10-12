// Hover popup (UI spec § 4.3). One shared, aria-hidden element moved between
// cards, for mouse devices only. Placement comes from placePopup, which keeps
// the popup off the player (YouTube Required Minimum Functionality).
// Edge handling is ported from ResponsibleAIEvidenceMark.astro, with the
// popup counted as part of its card's hover zone: it sits outside the card
// in the DOM but touches it on screen.
import { ATTR, MQ_FINE_POINTER, TESTID, onWatch } from '../../../lib/watch/contract';
import { placePopup, type Rect } from '../../../lib/watch/popup-position';
import { POPUP_CLOSE_DELAY_MS, POPUP_OPEN_DELAY_MS } from '../../../lib/watch/timings';
import type { WatchPlaylistView, WatchVideoView } from '../../../lib/watch/types';

function intersects(a: Rect, b: Rect): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

export function initPopup(root: HTMLElement, bus: EventTarget, data: WatchPlaylistView[]): void {
  const found = root.querySelector<HTMLElement>(`[data-testid="${TESTID.popup}"]`);
  if (!found) return;
  // Re-bound so the narrowing reaches the function declarations below.
  const popup: HTMLElement = found;
  const field = (name: string) => popup.querySelector<HTMLElement>(`.watch-popup__${name}`);
  const fields = {
    title: field('title'),
    channel: field('channel'),
    duration: field('duration'),
    date: field('date'),
    desc: field('desc'),
  };
  const playerFrame = root.querySelector<HTMLElement>(`[data-testid="${TESTID.playerFrame}"]`);
  const fine = window.matchMedia(MQ_FINE_POINTER);
  const thumbSelector = `[data-testid="${TESTID.thumb}"]`;

  const videos = new Map<string, WatchVideoView>();
  for (const playlist of data) {
    for (const video of playlist.videos) videos.set(`${playlist.slug}\n${video.id}`, video);
  }

  let openCard: HTMLElement | null = null;
  // Focusing a card that is not fully on screen scrolls it into view
  // (smoothly, under the site's scroll-behavior), and those scroll events
  // arrive after focusin. The popup follows its card until that scroll ends;
  // any other scroll closes it.
  let following = false;
  // Separate timers: crossing into a second card must neither cancel the
  // first one's close nor leave it open.
  let openTimer = 0;
  let closeTimer = 0;

  const cardOf = (target: EventTarget | null) =>
    target instanceof Element ? target.closest<HTMLElement>(thumbSelector) : null;
  const inPopup = (node: EventTarget | null) => node instanceof Node && popup.contains(node);
  const inZone = (node: EventTarget | null) =>
    node instanceof Node && ((openCard?.contains(node) ?? false) || popup.contains(node));

  function setText(el: HTMLElement | null, text: string) {
    if (!el) return;
    el.textContent = text;
    el.hidden = text === '';
  }

  function close() {
    window.clearTimeout(openTimer);
    window.clearTimeout(closeTimer);
    openCard = null;
    popup.hidden = true;
    popup.removeAttribute(ATTR.videoId);
  }

  function playerRect(): Rect | null {
    if (!playerFrame) return null;
    const rect = playerFrame.getBoundingClientRect();
    // A hidden player measures 0x0 and must not clamp anything.
    return rect.width > 0 && rect.height > 0 ? rect : null;
  }

  /** Returns false, closing the popup, when it would cover the player. */
  function place(card: HTMLElement): boolean {
    const size = { width: popup.offsetWidth, height: popup.offsetHeight };
    const viewport = { width: document.documentElement.clientWidth, height: window.innerHeight };
    const player = playerRect();
    const { top, left } = placePopup(card.getBoundingClientRect(), size, viewport, player);
    if (player && intersects({ top, left, right: left + size.width, bottom: top + size.height }, player)) {
      close();
      return false;
    }
    popup.style.top = `${top}px`;
    popup.style.left = `${left}px`;
    return true;
  }

  function open(card: HTMLElement, follow: boolean) {
    window.clearTimeout(openTimer);
    window.clearTimeout(closeTimer);
    const slug = card.getAttribute(ATTR.playlist);
    const id = card.getAttribute(ATTR.videoId);
    const video = slug && id ? videos.get(`${slug}\n${id}`) : undefined;
    if (!video || !id) return close();

    // API text goes in as text only.
    setText(fields.title, video.title);
    setText(fields.channel, video.channel);
    setText(fields.duration, video.durationText);
    setText(fields.date, video.publishedText);
    setText(fields.desc, video.description);
    popup.setAttribute(ATTR.videoId, id);

    // Unhide to measure, then place, all before the next paint.
    popup.hidden = false;
    if (!place(card)) return;
    openCard = card;
    following = follow;
  }

  // pointerover and pointerout bubble; a move between elements inside one
  // zone has its relatedTarget inside that zone too, so only real edge
  // crossings count.
  root.addEventListener('pointerover', (event) => {
    if (inPopup(event.target)) {
      window.clearTimeout(closeTimer);
      return;
    }
    const card = cardOf(event.target);
    if (!card || card.contains(event.relatedTarget as Node | null)) return;
    if (!fine.matches || event.pointerType !== 'mouse') return;
    if (openCard === card) {
      window.clearTimeout(closeTimer);
      return;
    }
    window.clearTimeout(openTimer);
    // Once one popup is open, the reader is browsing: swap without the wait.
    if (openCard) open(card, false);
    else openTimer = window.setTimeout(() => open(card, false), POPUP_OPEN_DELAY_MS);
  });

  root.addEventListener('pointerout', (event) => {
    const card = cardOf(event.target);
    const fromPopup = inPopup(event.target);
    if (!card && !fromPopup) return;
    const next = event.relatedTarget;
    if (card?.contains(next as Node | null) || (fromPopup && inPopup(next))) return;
    if (card && card !== openCard) window.clearTimeout(openTimer);
    if (!openCard || inZone(next)) return;
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(close, POPUP_CLOSE_DELAY_MS);
  });

  // Keyboard focus opens at once; a mouse click's focus does not match
  // :focus-visible. Touch devices never get the popup (§ 4.2).
  root.addEventListener('focusin', (event) => {
    const card = cardOf(event.target);
    if (!card || event.target !== card || !fine.matches || !card.matches(':focus-visible')) return;
    const { top, bottom } = card.getBoundingClientRect();
    open(card, top < 0 || bottom > window.innerHeight);
  });

  // The popup never takes focus, so leaving the card is leaving the zone.
  root.addEventListener('focusout', (event) => {
    if (openCard && event.target === openCard) close();
  });

  // Escape leaves focus where it is.
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close();
  });

  document.addEventListener('click', close, true);
  window.addEventListener('resize', close);
  window.addEventListener(
    'scroll',
    () => {
      if (!openCard) return;
      if (following && document.activeElement === openCard) place(openCard);
      else close();
    },
    { capture: true, passive: true },
  );
  window.addEventListener('scrollend', () => {
    following = false;
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') close();
  });
  fine.addEventListener('change', close);
  onWatch(bus, 'watch:playlist', close);
  onWatch(bus, 'watch:video', close);
}

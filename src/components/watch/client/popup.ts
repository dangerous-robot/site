// Hover popup (UI spec § 4.3). One shared, aria-hidden element moved between
// cards, for mouse devices only. Placement comes from placePopup, which keeps
// the popup off the player (YouTube Required Minimum Functionality).
// When to open and close comes from the shared card intent; this module adds
// the popup's own hover zone: it sits outside the card in the DOM but
// touches it on screen, so the pointer may cross into it.
import { ATTR, TESTID } from '../../../lib/watch/contract';
import { indexPlaylists } from '../../../lib/watch/index';
import { placePopup, rectsOverlap, type Rect } from '../../../lib/watch/popup-position';
import { POPUP_CLOSE_DELAY_MS } from '../../../lib/watch/timings';
import type { WatchPlaylistView } from '../../../lib/watch/types';
import { onCardIntent } from './cardIntent';
import { byTestId, setText } from './dom';

export function initPopup(root: HTMLElement, bus: EventTarget, data: WatchPlaylistView[]): void {
  const popup = byTestId(root, TESTID.popup);
  if (!popup) return;
  const field = (name: string) => popup.querySelector<HTMLElement>(`.watch-popup__${name}`);
  const fields = {
    title: field('title'),
    channel: field('channel'),
    duration: field('duration'),
    date: field('date'),
    desc: field('desc'),
  };
  const playerFrame = byTestId(root, TESTID.playerFrame);
  const index = indexPlaylists(data);

  let openCard: HTMLElement | null = null;
  // Focusing a card that is not fully on screen scrolls it into view
  // (smoothly, under the site's scroll-behavior), and those scroll events
  // arrive after focusin. The popup follows its card until that scroll ends;
  // any other scroll closes it.
  let following = false;
  let closeTimer = 0;

  const inPopup = (node: EventTarget | null) => node instanceof Node && popup.contains(node);

  const close = () => {
    window.clearTimeout(closeTimer);
    openCard = null;
    popup.hidden = true;
    popup.removeAttribute(ATTR.videoId);
  };

  const closeSoon = () => {
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(close, POPUP_CLOSE_DELAY_MS);
  };

  const playerRect = (): Rect | null => {
    if (!playerFrame) return null;
    const rect = playerFrame.getBoundingClientRect();
    // A hidden player measures 0x0 and must not clamp anything.
    return rect.width > 0 && rect.height > 0 ? rect : null;
  };

  /** Returns false, closing the popup, when it would cover the player. */
  const place = (card: HTMLElement): boolean => {
    const size = { width: popup.offsetWidth, height: popup.offsetHeight };
    const viewport = { width: document.documentElement.clientWidth, height: window.innerHeight };
    const player = playerRect();
    const { top, left } = placePopup(card.getBoundingClientRect(), size, viewport, player);
    if (player && rectsOverlap({ top, left, right: left + size.width, bottom: top + size.height }, player)) {
      close();
      return false;
    }
    popup.style.top = `${top}px`;
    popup.style.left = `${left}px`;
    return true;
  };

  const open = (card: HTMLElement, follow: boolean) => {
    window.clearTimeout(closeTimer);
    const id = card.getAttribute(ATTR.videoId) ?? '';
    const found = index.findVideo(card.getAttribute(ATTR.playlist) ?? '', id);
    if (!found) return close();
    const { video } = found;

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
  };

  onCardIntent(root, bus, {
    enter: (card) => {
      if (card === openCard) window.clearTimeout(closeTimer);
      // Once one popup is open, the reader is browsing: swap without the wait.
      else if (openCard) open(card, false);
    },
    rest: (card, source) => {
      if (card === openCard) return;
      const { top, bottom } = card.getBoundingClientRect();
      open(card, source === 'keyboard' && (top < 0 || bottom > window.innerHeight));
    },
    leave: (card, how, to) => {
      if (card !== openCard) return;
      // The popup never takes focus, so focus leaving the card leaves the zone.
      if (how === 'focus') close();
      else if (!inPopup(to)) closeSoon();
    },
    cancel: close,
  });

  popup.addEventListener('pointerover', () => window.clearTimeout(closeTimer));
  popup.addEventListener('pointerout', (event) => {
    const to = event.relatedTarget;
    if (!openCard || inPopup(to) || (to instanceof Node && openCard.contains(to))) return;
    closeSoon();
  });

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
}

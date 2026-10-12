// Card behaviour (UI spec § 4.2). Cards are YouTube links so they work
// without JavaScript; here a plain click (or Enter, which fires the same
// click) plays in the page instead. Modified clicks keep the link, and a
// middle click never reaches this handler (it fires auxclick).
import { ATTR, CLASS, TESTID, emitWatch, onWatch } from '../../../lib/watch/contract';
import type { WatchPlaylistView } from '../../../lib/watch/types';
import { closestThumb, isPlainClick, testid } from './dom';

function setPlaying(card: HTMLElement, playing: boolean): void {
  if (playing) card.setAttribute('aria-current', 'true');
  else card.removeAttribute('aria-current');
  const label = card.querySelector<HTMLElement>(`.${CLASS.thumbPlaying}`);
  if (label) label.hidden = !playing;
}

export function initGrid(root: HTMLElement, bus: EventTarget, _data: WatchPlaylistView[]): void {
  root.addEventListener('click', (event) => {
    if (event.defaultPrevented || !isPlainClick(event)) return;
    const card = closestThumb(event.target);
    const slug = card?.getAttribute(ATTR.playlist);
    const id = card?.getAttribute(ATTR.videoId);
    if (!slug || !id) return;
    event.preventDefault();
    emitWatch(bus, 'watch:video', { slug, id, play: true, notice: false });
  });

  let marked: HTMLElement | null = null;

  // Marked at once, before the player's autoplay gate inserts anything, so
  // the reader sees which card they picked while the player scrolls in.
  const markPlaying = ({ slug, id }: { slug: string; id: string }) => {
    const card = root.querySelector<HTMLElement>(
      `${testid(TESTID.thumb)}[${ATTR.playlist}="${CSS.escape(slug)}"][${ATTR.videoId}="${CSS.escape(id)}"]`,
    );
    if (card === marked) return;
    if (marked) setPlaying(marked, false);
    if (card) setPlaying(card, true);
    marked = card;
  };

  // play: false only shows a poster, so it leaves the marks alone.
  onWatch(bus, 'watch:video', (detail) => {
    if (detail.play) markPlaying(detail);
  });
  onWatch(bus, 'watch:play', markPlaying);
}

// Card behaviour (UI spec § 4.2). Cards are YouTube links so they work
// without JavaScript; here a plain click (or Enter, which fires the same
// click) plays in the page instead. Modified clicks keep the link, and a
// middle click never reaches this handler (it fires auxclick).
import { ATTR, CLASS, TESTID, emitWatch, onWatch } from '../../../lib/watch/contract';
import type { WatchPlaylistView } from '../../../lib/watch/types';

export function initGrid(root: HTMLElement, bus: EventTarget, _data: WatchPlaylistView[]): void {
  const thumbSelector = `[data-testid="${TESTID.thumb}"]`;
  const thumbs = [...root.querySelectorAll<HTMLElement>(thumbSelector)];

  root.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const card = event.target instanceof Element ? event.target.closest<HTMLElement>(thumbSelector) : null;
    const slug = card?.getAttribute(ATTR.playlist);
    const id = card?.getAttribute(ATTR.videoId);
    if (!slug || !id) return;
    event.preventDefault();
    emitWatch(bus, 'watch:video', { slug, id, play: true, notice: false });
  });

  // Marked at once, before the player's autoplay gate inserts anything, so
  // the reader sees which card they picked while the player scrolls in.
  const markPlaying = ({ slug, id }: { slug: string; id: string }) => {
    for (const thumb of thumbs) {
      const playing = thumb.getAttribute(ATTR.playlist) === slug && thumb.getAttribute(ATTR.videoId) === id;
      if (playing) thumb.setAttribute('aria-current', 'true');
      else thumb.removeAttribute('aria-current');
      const label = thumb.querySelector<HTMLElement>(`.${CLASS.thumbPlaying}`);
      if (label) label.hidden = !playing;
    }
  };

  // play: false only shows a poster, so it leaves the marks alone.
  onWatch(bus, 'watch:video', (detail) => {
    if (detail.play) markPlaying(detail);
  });
  onWatch(bus, 'watch:play', markPlaying);
}

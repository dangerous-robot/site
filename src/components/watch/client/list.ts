// Video row behaviour. Rows are YouTube links so they work without
// JavaScript; here a plain click (or Enter, which fires the same click)
// plays in the page instead. Modified clicks keep the link, and a middle
// click never reaches this handler (it fires auxclick). The current mark
// follows the video in the player, poster or playing.
import { ATTR, CLASS, TESTID, emitWatch, onWatch } from '../../../lib/watch/contract';
import type { WatchPlaylistView } from '../../../lib/watch/types';
import { closestByTestId, isPlainClick, testid } from './dom';

function setCurrent(row: HTMLElement, current: boolean): void {
  if (current) row.setAttribute('aria-current', 'true');
  else row.removeAttribute('aria-current');
  const badge = row.querySelector<HTMLElement>(`.${CLASS.thumbPlaying}`);
  if (badge) badge.hidden = !current;
}

export function initList(root: HTMLElement, bus: EventTarget, _data: WatchPlaylistView[]): void {
  root.addEventListener('click', (event) => {
    if (event.defaultPrevented || !isPlainClick(event)) return;
    const row = closestByTestId(event.target, TESTID.thumb);
    const slug = row?.getAttribute(ATTR.playlist);
    const id = row?.getAttribute(ATTR.videoId);
    if (!slug || !id) return;
    event.preventDefault();
    emitWatch(bus, 'watch:video', { slug, id, play: true, notice: false });
  });

  // Nothing is marked by the server, which cannot know the URL's video;
  // main.ts emits the arrival poster's watch:video.
  let marked: HTMLElement | null = null;

  onWatch(bus, 'watch:video', ({ slug, id }) => {
    const row = root.querySelector<HTMLElement>(
      `${testid(TESTID.thumb)}[${ATTR.playlist}="${CSS.escape(slug)}"][${ATTR.videoId}="${CSS.escape(id)}"]`,
    );
    if (row === marked) return;
    if (marked) setCurrent(marked, false);
    if (row) setCurrent(row, true);
    marked = row;
  });
}

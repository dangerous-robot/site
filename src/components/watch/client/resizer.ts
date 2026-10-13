// Drag handle between the list column and the player. A separator with a
// value, so arrow keys resize it too (Shift for bigger steps, Home and End
// for the limits). Hidden by CSS when the columns stack.
import { LIST_WIDTH, TESTID } from '../../../lib/watch/contract';
import { clampListWidth } from '../../../lib/watch/layout';
import type { WatchPlaylistView } from '../../../lib/watch/types';
import { byTestId } from './dom';

export function initResizer(root: HTMLElement, _bus: EventTarget, _data: WatchPlaylistView[]): void {
  const handle = byTestId(root, TESTID.resizer);
  const column = byTestId(root, TESTID.listCol);
  if (!handle || !column) return;

  const setWidth = (px: number) => {
    const width = clampListWidth(px);
    column.style.setProperty('--watch-list-w', `${width}px`);
    handle.setAttribute('aria-valuenow', String(width));
  };

  let drag: { x: number; width: number } | null = null;

  handle.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    drag = { x: event.clientX, width: column.getBoundingClientRect().width };
  });
  handle.addEventListener('pointermove', (event) => {
    if (drag) setWidth(drag.width + event.clientX - drag.x);
  });
  const end = () => {
    drag = null;
  };
  handle.addEventListener('pointerup', end);
  handle.addEventListener('pointercancel', end);

  handle.addEventListener('keydown', (event) => {
    const now = column.getBoundingClientRect().width;
    const step = event.shiftKey ? LIST_WIDTH.bigStep : LIST_WIDTH.step;
    let next: number;
    switch (event.key) {
      case 'ArrowRight':
        next = now + step;
        break;
      case 'ArrowLeft':
        next = now - step;
        break;
      case 'Home':
        next = LIST_WIDTH.min;
        break;
      case 'End':
        next = LIST_WIDTH.max;
        break;
      default:
        return;
    }
    event.preventDefault();
    setWidth(next);
  });
}

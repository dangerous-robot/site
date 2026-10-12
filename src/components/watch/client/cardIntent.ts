// Which card a reader is attending to, shared by the hover popup and the
// frame preview (UI spec § 4.1 to § 4.4). One tracker per page, so both
// count their delays from the same moment and close on the same events.
//
// A mouse rests on a card once it has not moved over it for REST_MS; keyboard
// focus (:focus-visible, on a device with a mouse) counts as rest at once.
// Touch and pen never rest. After a cancel nothing restarts until the
// pointer crosses into a card again or focus moves to one.
import { onWatch } from '../../../lib/watch/contract';
import { POPUP_OPEN_DELAY_MS } from '../../../lib/watch/timings';
import { closestThumb, finePointer } from './dom';

/** The popup opens and frames start loading (FRAME_LOAD_AT_MS) at the same moment. */
const REST_MS = POPUP_OPEN_DELAY_MS;

export type IntentSource = 'pointer' | 'keyboard';

export interface CardIntentListener {
  /** The mouse crossed into a card; rest may follow. */
  enter?(card: HTMLElement): void;
  /** restedMs is how long ago the rest began: REST_MS for a mouse, 0 for keyboard focus. */
  rest?(card: HTMLElement, source: IntentSource, restedMs: number): void;
  /** The mouse left the card for `to`, or focus left it. */
  leave?(card: HTMLElement, how: 'pointer' | 'focus', to: EventTarget | null): void;
  /** Escape, any click, the tab hidden, the pointer type changing, or a playlist or video change. */
  cancel?(): void;
}

interface Tracker {
  listeners: CardIntentListener[];
}

const trackers = new WeakMap<HTMLElement, Tracker>();

export function onCardIntent(root: HTMLElement, bus: EventTarget, listener: CardIntentListener): void {
  let tracker = trackers.get(root);
  if (!tracker) {
    tracker = createTracker(root, bus);
    trackers.set(root, tracker);
  }
  tracker.listeners.push(listener);
}

function createTracker(root: HTMLElement, bus: EventTarget): Tracker {
  const listeners: CardIntentListener[] = [];
  const fine = finePointer();
  let current: { card: HTMLElement; source: IntentSource; rested: boolean } | null = null;
  let restTimer = 0;

  const each = (call: (listener: CardIntentListener) => void) => {
    for (const listener of listeners) call(listener);
  };

  const rested = () => {
    if (!current || current.rested) return;
    current.rested = true;
    const { card, source } = current;
    each((l) => l.rest?.(card, source, REST_MS));
  };

  // One timer, re-armed by each move until it fires.
  const armRest = () => {
    window.clearTimeout(restTimer);
    restTimer = window.setTimeout(rested, REST_MS);
  };

  const end = (how: 'pointer' | 'focus', to: EventTarget | null) => {
    if (!current) return;
    const { card } = current;
    window.clearTimeout(restTimer);
    current = null;
    each((l) => l.leave?.(card, how, to));
  };

  const cancel = () => {
    window.clearTimeout(restTimer);
    current = null;
    each((l) => l.cancel?.());
  };

  // pointerover and pointerout bubble; a move between elements inside one
  // card has its relatedTarget inside that card too, so only real edge
  // crossings count.
  root.addEventListener('pointerover', (event) => {
    if (event.pointerType !== 'mouse' || !fine.matches) return;
    const card = closestThumb(event.target);
    if (!card || card === current?.card || card.contains(event.relatedTarget as Node | null)) return;
    current = { card, source: 'pointer', rested: false };
    armRest();
    each((l) => l.enter?.(card));
  });

  root.addEventListener(
    'pointermove',
    (event) => {
      if (current?.source === 'pointer' && !current.rested && event.pointerType === 'mouse') armRest();
    },
    { passive: true },
  );

  root.addEventListener('pointerout', (event) => {
    if (event.pointerType !== 'mouse') return;
    const card = closestThumb(event.target);
    if (!card || card !== current?.card || card.contains(event.relatedTarget as Node | null)) return;
    end('pointer', event.relatedTarget);
  });

  // A mouse click's focus does not match :focus-visible, so only keyboard
  // focus counts here.
  root.addEventListener('focusin', (event) => {
    const card = closestThumb(event.target);
    if (!card || event.target !== card || !fine.matches || !card.matches(':focus-visible')) return;
    window.clearTimeout(restTimer);
    current = { card, source: 'keyboard', rested: true };
    each((l) => l.rest?.(card, 'keyboard', 0));
  });

  root.addEventListener('focusout', (event) => {
    if (current && event.target === current.card) end('focus', event.relatedTarget);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') cancel();
  });
  document.addEventListener('click', cancel, true);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') cancel();
  });
  fine.addEventListener('change', cancel);
  onWatch(bus, 'watch:playlist', cancel);
  onWatch(bus, 'watch:video', cancel);

  return { listeners };
}

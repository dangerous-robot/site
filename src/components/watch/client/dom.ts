// DOM helpers shared by the /watch client controllers.
import { MQ_FINE_POINTER, MQ_REDUCED_MOTION, TESTID } from '../../../lib/watch/contract';

type TestId = (typeof TESTID)[keyof typeof TESTID];

export function testid(id: TestId): string {
  return `[data-testid="${id}"]`;
}

export function byTestId<T extends Element = HTMLElement>(scope: ParentNode, id: TestId): T | null {
  return scope.querySelector<T>(testid(id));
}

export function allByTestId<T extends Element = HTMLElement>(scope: ParentNode, id: TestId): T[] {
  return [...scope.querySelectorAll<T>(testid(id))];
}

export function closestByTestId(target: EventTarget | null, id: TestId): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>(testid(id)) : null;
}

/** The video card an event target sits in, if any. */
export function closestThumb(target: EventTarget | null): HTMLElement | null {
  return closestByTestId(target, TESTID.thumb);
}

/** A primary click with no modifier key; anything else keeps the link's own behaviour. */
export function isPlainClick(event: MouseEvent): boolean {
  return event.button === 0 && !(event.ctrlKey || event.metaKey || event.shiftKey || event.altKey);
}

/** API text goes in as text only. An empty element is hidden, or it would still take a flex gap. */
export function setText(el: HTMLElement | null, text: string): void {
  if (!el) return;
  el.textContent = text;
  el.hidden = text === '';
}

// One MediaQueryList per query for the page, created on first use so that
// importing this module touches no DOM globals.
let finePointerList: MediaQueryList | undefined;
let osReduceList: MediaQueryList | undefined;

/** Popups and previews are for mouse devices only. */
export function finePointer(): MediaQueryList {
  finePointerList ??= window.matchMedia(MQ_FINE_POINTER);
  return finePointerList;
}

export function osReduceMotion(): MediaQueryList {
  osReduceList ??= window.matchMedia(MQ_REDUCED_MOTION);
  return osReduceList;
}

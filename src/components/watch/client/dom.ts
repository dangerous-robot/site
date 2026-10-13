// DOM helpers shared by the /watch client controllers.
import { TESTID } from '../../../lib/watch/contract';

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

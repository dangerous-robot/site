// Playlist tab behaviour (UI spec § 4.6). Renders aria-selected and the
// roving tabindex from every watch:playlist (main.ts emits one at startup).
// A click on a tab that is not selected emits watch:playlist; Enter and
// Space reach the same click. Arrows, Home and End move focus only, and
// focus leaving the list puts the roving 0 back on the selected tab.
// main.ts shows the panel, rewrites the URL and announces.
import { ATTR, TESTID, emitWatch, onWatch } from '../../../lib/watch/contract';
import type { WatchPlaylistView } from '../../../lib/watch/types';
import { allByTestId, byTestId, closestByTestId } from './dom';

function slugOf(tab: HTMLElement): string {
  return tab.getAttribute(ATTR.playlist) ?? '';
}

function isSelected(tab: HTMLElement): boolean {
  return tab.getAttribute('aria-selected') === 'true';
}

function setRoving(tabs: HTMLElement[], active: HTMLElement): void {
  for (const tab of tabs) tab.tabIndex = tab === active ? 0 : -1;
}

export function initTabs(root: HTMLElement, bus: EventTarget, _data: WatchPlaylistView[]): void {
  const tablist = byTestId(root, TESTID.tablist);
  if (!tablist) return;
  const tabs = allByTestId(tablist, TESTID.tab);
  if (tabs.length === 0) return;

  onWatch(bus, 'watch:playlist', ({ slug }) => {
    const target = tabs.find((tab) => slugOf(tab) === slug);
    if (!target) return;
    for (const tab of tabs) tab.setAttribute('aria-selected', tab === target ? 'true' : 'false');
    setRoving(tabs, target);
  });

  // Buttons turn Enter and Space into a click, so this one handler covers
  // mouse, touch and keyboard selection. The selected tab emits nothing.
  tablist.addEventListener('click', (event) => {
    const tab = closestByTestId(event.target, TESTID.tab);
    if (!tab || isSelected(tab)) return;
    emitWatch(bus, 'watch:playlist', { slug: slugOf(tab) });
  });

  // Manual activation: arrows only move focus, so a reader can pass over a
  // playlist without loading its panel.
  tablist.addEventListener('keydown', (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const current = tabs.indexOf(event.target as HTMLElement);
    if (current < 0) return;
    const last = tabs.length - 1;
    let next: number;
    switch (event.key) {
      case 'ArrowUp':
      case 'ArrowLeft':
        next = current === 0 ? last : current - 1;
        break;
      case 'ArrowDown':
      case 'ArrowRight':
        next = current === last ? 0 : current + 1;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = last;
        break;
      default:
        return;
    }
    event.preventDefault();
    setRoving(tabs, tabs[next]);
    tabs[next].focus();
  });

  // After arrowing past tabs without choosing one, Tab back into the list
  // should land on the selected tab, not the last one focused.
  tablist.addEventListener('focusout', (event) => {
    const to = event.relatedTarget;
    if (to instanceof Node && tablist.contains(to)) return;
    const selected = tabs.find(isSelected);
    if (selected) setRoving(tabs, selected);
  });
}

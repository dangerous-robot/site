// Playlist tab behaviour (UI spec § 4.6). Contract: render aria-selected and
// the roving tabindex from every watch:playlist (main.ts emits one at
// startup for a deep-linked list); on a reader's Enter or Space, emit
// watch:playlist. main.ts shows the panel, rewrites the URL and announces.
import type { WatchPlaylistView } from '../../../lib/watch/types';

export function initTabs(_root: HTMLElement, _bus: EventTarget, _data: WatchPlaylistView[]): void {}

// Card behaviour (UI spec § 4.2). Contract: a plain click or Enter on a card
// emits watch:video with play: true; modified and middle clicks keep the
// link. Mark the playing card on watch:video with play: true and on
// watch:play, never on play: false.
import type { WatchPlaylistView } from '../../../lib/watch/types';

export function initGrid(_root: HTMLElement, _bus: EventTarget, _data: WatchPlaylistView[]): void {}

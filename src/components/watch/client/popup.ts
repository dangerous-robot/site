// Hover popup behaviour (UI spec § 4.3). Contract: one shared popup for
// mouse devices, placed with placePopup so it never covers the player;
// close it on watch:playlist and watch:video.
import type { WatchPlaylistView } from '../../../lib/watch/types';

export function initPopup(_root: HTMLElement, _bus: EventTarget, _data: WatchPlaylistView[]): void {}

// Player behaviour (UI spec § 4.7). Contract: render every watch:video
// (play: false swaps the poster and shows the notice only when notice is
// true; play: true also inserts the iframe once the frame is at least half
// in view); emit watch:play when the iframe goes in.
import type { WatchPlaylistView } from '../../../lib/watch/types';

export function initPlayer(_root: HTMLElement, _bus: EventTarget, _data: WatchPlaylistView[]): void {}

// Hover previews switch and frame cycling (UI spec § 4.4, § 4.5). Contract:
// emit watch:preview when the effective setting changes; stop any cycle on
// watch:playlist and watch:video.
import type { WatchPlaylistView } from '../../../lib/watch/types';

export function initPreview(_root: HTMLElement, _bus: EventTarget, _data: WatchPlaylistView[]): void {}

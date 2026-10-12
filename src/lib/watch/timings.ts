// Interaction timings for /watch (UI spec § 4.1). All delays count from when
// the pointer comes to rest on a card or keyboard focus arrives. Tests step
// through them with Playwright's page.clock, so page code has no test hooks.

/** Longer than the evidence marks' 150ms so crossing the grid of large cards does not flash popups. */
export const POPUP_OPEN_DELAY_MS = 300;
export const POPUP_CLOSE_DELAY_MS = 150;
export const POPUP_FADE_MS = 150;

/** Frames start loading at the same moment the popup opens. */
export const FRAME_LOAD_AT_MS = 300;
/** First frame shows here, or when it finishes loading if later. */
export const FRAME_FIRST_AT_MS = 600;
export const FRAME_INTERVAL_MS = 900;
export const FRAME_FADE_MS = 200;

/** Crossfade length; frames swap without a fade under a reduce-motion setting. */
export function frameFadeMs(reduceMotion: boolean): number {
  return reduceMotion ? 0 : FRAME_FADE_MS;
}

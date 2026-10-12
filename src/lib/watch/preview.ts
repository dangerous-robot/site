// Hover preview rule and frame cycler for /watch (UI spec § 4.4 and § 4.5).
// The clock and image loader are injected so unit tests drive the timeline
// with a fake clock; client/preview.ts supplies the real ones. Nothing here
// touches DOM globals until a function is called.
import type { PreviewsStoredValue } from './contract';
import { isPlaceholder } from './frames';
import { FRAME_FIRST_AT_MS, FRAME_INTERVAL_MS, FRAME_LOAD_AT_MS } from './timings';

/** localStorage can hold anything a reader or extension wrote; only on and off count as a choice. */
export function parseStoredPreviews(raw: string | null | undefined): PreviewsStoredValue | null {
  return raw === 'on' || raw === 'off' ? raw : null;
}

/** An explicit choice wins; with none, either reduce-motion signal turns previews off. */
export function previewsEnabled(stored: PreviewsStoredValue | null, osReduce: boolean, siteReduce: boolean): boolean {
  if (stored !== null) return stored === 'on';
  return !(osReduce || siteReduce);
}

/** "Off because reduce motion is on." shows only when the setting, not the reader, turned previews off. */
export function previewsHintShown(stored: PreviewsStoredValue | null, osReduce: boolean, siteReduce: boolean): boolean {
  return stored === null && (osReduce || siteReduce);
}

export interface Clock {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

/** Reads the timer functions at call time, so importing this module stays side-effect free. */
export const systemClock: Clock = {
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as Parameters<typeof globalThis.clearTimeout>[0]),
};

/**
 * Calls done once with whether the frame is usable. done may run
 * synchronously (a cache hit). May return a cancel function that stops done
 * from being called.
 */
export type FrameLoader = (url: string, done: (ok: boolean) => void) => (() => void) | void;

/**
 * Loads through Image() objects. The policy is set before src because
 * assigning src starts the request. A 404 frame can arrive as a 120px grey
 * image without firing onerror, so width is checked too.
 */
export function imageFrameLoader(createImage: () => HTMLImageElement): FrameLoader {
  return (url, done) => {
    const img = createImage();
    img.referrerPolicy = 'no-referrer';
    img.onload = () => done(!isPlaceholder(img.naturalWidth));
    img.onerror = () => done(false);
    img.src = url;
  };
}

/**
 * Remembers each URL's result for the page's life, so a second hover on a
 * card makes no new requests. The caller owns the cache, which keeps test
 * runs independent.
 */
export function createFrameCache(load: FrameLoader): FrameLoader {
  type Entry = { ok: boolean | null; waiters: ((ok: boolean) => void)[] };
  const entries = new Map<string, Entry>();
  return (url, done) => {
    const hit = entries.get(url);
    if (hit && hit.ok !== null) {
      done(hit.ok);
      return;
    }
    const entry: Entry = hit ?? { ok: null, waiters: [] };
    entry.waiters.push(done);
    if (!hit) {
      // Stored before load runs, so a synchronous loader still finds its waiter.
      entries.set(url, entry);
      load(url, (ok) => {
        if (entry.ok !== null) return;
        entry.ok = ok;
        const waiters = entry.waiters;
        entry.waiters = [];
        for (const waiter of waiters) waiter(ok);
      });
    }
    // A stopped cycle's callback would otherwise stay referenced until the
    // shared load finishes, which may be never on a stalled request.
    return () => {
      const at = entry.waiters.indexOf(done);
      if (at !== -1) entry.waiters.splice(at, 1);
    };
  };
}

export interface FrameCycleOptions {
  /** From frameUrls, in cycle order. */
  urls: readonly string[];
  /**
   * How long ago the reader came to rest, when the cycle starts late. A
   * cycle started when the popup opens passes FRAME_LOAD_AT_MS and requests
   * its frames at once. Default 0.
   */
  elapsedMs?: number;
  clock: Clock;
  load: FrameLoader;
  /** frame is 1-based, the value for data-frame. */
  onFrame: (frame: number, url: string) => void;
  /** Called once by stop() if any frame was shown, so the caller puts the cover back. */
  onRestore?: () => void;
  /** Every frame failed: the card gets no preview and the cycle ends by itself. */
  onNoPreview?: () => void;
}

export interface FrameCycle {
  /** Idempotent. Late load results after stop show nothing. */
  stop(): void;
}

type FrameStatus = 'pending' | 'ok' | 'failed';

/**
 * Timeline from rest (pointer rest or keyboard focus): request every frame
 * at FRAME_LOAD_AT_MS; show the first usable one at FRAME_FIRST_AT_MS, or
 * when it loads if later; then move to the next usable frame every
 * FRAME_INTERVAL_MS. Failed frames are skipped and a frame still loading at
 * a tick waits for the next lap.
 */
export function startFrameCycle(options: FrameCycleOptions): FrameCycle {
  const { urls, clock, load, onFrame, onRestore, onNoPreview, elapsedMs = 0 } = options;
  const statuses: FrameStatus[] = urls.map(() => 'pending');
  const timers = new Set<unknown>();
  const cancels: (() => void)[] = [];
  let stopped = false;
  let firstDue = false;
  let current = -1;

  function after(ms: number, fn: () => void): void {
    // onFrame may call stop() synchronously; show() schedules after it returns.
    if (stopped) return;
    const handle = clock.setTimeout(() => {
      timers.delete(handle);
      fn();
    }, ms);
    timers.add(handle);
  }

  function end(): void {
    stopped = true;
    for (const handle of timers) clock.clearTimeout(handle);
    timers.clear();
    for (const cancel of cancels) cancel();
    cancels.length = 0;
  }

  function show(index: number): void {
    current = index;
    onFrame(index + 1, urls[index]);
    after(FRAME_INTERVAL_MS, tick);
  }

  function tick(): void {
    for (let step = 1; step < urls.length; step++) {
      const next = (current + step) % urls.length;
      if (statuses[next] === 'ok') {
        show(next);
        return;
      }
    }
    // Only the current frame is usable so far: keep it without re-emitting,
    // and check again only while another frame could still load.
    if (statuses.includes('pending')) after(FRAME_INTERVAL_MS, tick);
  }

  function evaluateFirst(): void {
    if (stopped || current !== -1) return;
    if (statuses.every((s) => s === 'failed')) {
      end();
      onNoPreview?.();
      return;
    }
    if (!firstDue) return;
    // Order is 1, 2, 3, so a pending earlier frame is waited for rather than jumped.
    const index = statuses.findIndex((s) => s !== 'failed');
    if (statuses[index] === 'ok') show(index);
  }

  function requestAll(): void {
    urls.forEach((url, index) => {
      const cancel = load(url, (ok) => {
        if (stopped || statuses[index] !== 'pending') return;
        statuses[index] = ok ? 'ok' : 'failed';
        evaluateFirst();
      });
      if (cancel) cancels.push(cancel);
    });
    evaluateFirst();
  }

  function firstNowDue(): void {
    firstDue = true;
    evaluateFirst();
  }

  // A moment already past runs now, not on a zero timer: fake clocks push a
  // zero delay scheduled inside a timer to the next millisecond.
  const atOrNow = (at: number, fn: () => void) => (at <= elapsedMs ? fn() : after(at - elapsedMs, fn));
  atOrNow(FRAME_LOAD_AT_MS, requestAll);
  atOrNow(FRAME_FIRST_AT_MS, firstNowDue);

  return {
    stop() {
      if (stopped) return;
      const shown = current !== -1;
      end();
      if (shown) onRestore?.();
    },
  };
}

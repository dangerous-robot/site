import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createFrameCache,
  imageFrameLoader,
  parseStoredPreviews,
  previewsEnabled,
  previewsHintShown,
  startFrameCycle,
  type Clock,
  type FrameLoader,
} from './preview';
import { frameUrls } from './frames';
import { FRAME_FIRST_AT_MS, FRAME_INTERVAL_MS, FRAME_LOAD_AT_MS } from './timings';

/** Runs timers in due order, including ones scheduled while advancing. */
class FakeClock implements Clock {
  now = 0;
  private seq = 0;
  readonly timers = new Map<number, { at: number; fn: () => void }>();

  setTimeout(fn: () => void, ms: number): number {
    const id = ++this.seq;
    this.timers.set(id, { at: this.now + ms, fn });
    return id;
  }

  clearTimeout(handle: unknown): void {
    this.timers.delete(handle as number);
  }

  advanceTo(target: number): void {
    for (;;) {
      let nextId = -1;
      let nextAt = Infinity;
      for (const [id, timer] of this.timers) {
        if (timer.at <= target && timer.at < nextAt) {
          nextId = id;
          nextAt = timer.at;
        }
      }
      if (nextId === -1) break;
      const timer = this.timers.get(nextId)!;
      this.timers.delete(nextId);
      this.now = timer.at;
      timer.fn();
    }
    this.now = target;
  }
}

/** Records requests; tests resolve them by hand, or at once with `auto`. */
class FakeLoader {
  readonly requests: string[] = [];
  private readonly pending = new Map<string, ((ok: boolean) => void)[]>();
  constructor(private readonly auto?: (url: string) => boolean) {}

  readonly load: FrameLoader = (url, done) => {
    this.requests.push(url);
    if (this.auto) {
      done(this.auto(url));
      return;
    }
    this.pending.set(url, [...(this.pending.get(url) ?? []), done]);
  };

  resolve(url: string, ok: boolean): void {
    const waiters = this.pending.get(url) ?? [];
    this.pending.delete(url);
    for (const done of waiters) done(ok);
  }
}

const URLS = frameUrls('aaaaaaaaaa1', 'sd');

function run(loader: FrameLoader, urls: readonly string[] = URLS) {
  const clock = new FakeClock();
  const shown: { frame: number; at: number }[] = [];
  let restored = 0;
  let noPreview = 0;
  const cycle = startFrameCycle({
    urls,
    clock,
    load: loader,
    onFrame: (frame) => shown.push({ frame, at: clock.now }),
    onRestore: () => restored++,
    onNoPreview: () => noPreview++,
  });
  return {
    clock,
    cycle,
    shown,
    frames: () => shown.map((s) => s.frame),
    restored: () => restored,
    noPreview: () => noPreview,
  };
}

describe('previewsEnabled and the hint (UI spec § 4.5 truth table)', () => {
  const rows: [stored: 'on' | 'off' | null, os: boolean, site: boolean, enabled: boolean, hint: boolean][] = [
    ['on', false, false, true, false],
    ['on', true, false, true, false],
    ['on', false, true, true, false],
    ['on', true, true, true, false],
    ['off', false, false, false, false],
    ['off', true, false, false, false],
    ['off', false, true, false, false],
    ['off', true, true, false, false],
    [null, true, false, false, true],
    [null, false, true, false, true],
    [null, true, true, false, true],
    [null, false, false, true, false],
  ];
  for (const [stored, os, site, enabled, hint] of rows) {
    test(`stored ${stored ?? 'none'}, OS reduce ${os}, site reduce ${site}: ${enabled ? 'on' : 'off'}${hint ? ' with hint' : ''}`, () => {
      assert.equal(previewsEnabled(stored, os, site), enabled);
      assert.equal(previewsHintShown(stored, os, site), hint);
    });
  }

  test('parseStoredPreviews keeps on and off and treats anything else as no choice', () => {
    assert.equal(parseStoredPreviews('on'), 'on');
    assert.equal(parseStoredPreviews('off'), 'off');
    for (const raw of [null, undefined, '', 'true', 'ON', 'reduce']) {
      assert.equal(parseStoredPreviews(raw), null, String(raw));
    }
  });
});

describe('startFrameCycle with a fake clock (UI spec § 4.4)', () => {
  test('nothing is requested before FRAME_LOAD_AT_MS, then all three frames in order', () => {
    const loader = new FakeLoader();
    const { clock } = run(loader.load);
    clock.advanceTo(FRAME_LOAD_AT_MS - 1);
    assert.deepEqual(loader.requests, []);
    clock.advanceTo(FRAME_LOAD_AT_MS);
    assert.deepEqual(loader.requests, URLS);
  });

  test('first frame shows at FRAME_FIRST_AT_MS, then advances every FRAME_INTERVAL_MS and loops', () => {
    const t = run(new FakeLoader(() => true).load);
    t.clock.advanceTo(FRAME_FIRST_AT_MS - 1);
    assert.deepEqual(t.shown, []);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 3 * FRAME_INTERVAL_MS);
    assert.deepEqual(t.shown, [
      { frame: 1, at: FRAME_FIRST_AT_MS },
      { frame: 2, at: FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS },
      { frame: 3, at: FRAME_FIRST_AT_MS + 2 * FRAME_INTERVAL_MS },
      { frame: 1, at: FRAME_FIRST_AT_MS + 3 * FRAME_INTERVAL_MS },
    ]);
  });

  test('a slow first frame shows when it loads, and the interval counts from then', () => {
    const loader = new FakeLoader();
    const t = run(loader.load);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 200);
    assert.deepEqual(t.shown, []);
    for (const url of URLS) loader.resolve(url, true);
    assert.deepEqual(t.shown, [{ frame: 1, at: FRAME_FIRST_AT_MS + 200 }]);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 200 + FRAME_INTERVAL_MS);
    assert.deepEqual(t.frames(), [1, 2]);
  });

  test('a failed middle frame is skipped every lap', () => {
    const t = run(new FakeLoader((url) => !url.endsWith('2.jpg')).load);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 4 * FRAME_INTERVAL_MS);
    assert.deepEqual(t.frames(), [1, 3, 1, 3, 1]);
  });

  test('a failed first frame starts the cycle at frame 2', () => {
    const t = run(new FakeLoader((url) => !url.endsWith('1.jpg')).load);
    t.clock.advanceTo(FRAME_FIRST_AT_MS);
    assert.deepEqual(t.shown, [{ frame: 2, at: FRAME_FIRST_AT_MS }]);
  });

  test('a frame still loading at a tick is passed over until it loads', () => {
    const loader = new FakeLoader();
    const t = run(loader.load);
    t.clock.advanceTo(FRAME_LOAD_AT_MS);
    loader.resolve(URLS[0], true);
    loader.resolve(URLS[2], true);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS);
    assert.deepEqual(t.frames(), [1, 3]);
    loader.resolve(URLS[1], true);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 3 * FRAME_INTERVAL_MS);
    assert.deepEqual(t.frames(), [1, 3, 1, 2]);
  });

  test('only one usable frame: shown once, never re-emitted, and no timer left running', () => {
    const t = run(new FakeLoader((url) => url.endsWith('3.jpg')).load);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 5 * FRAME_INTERVAL_MS);
    assert.deepEqual(t.frames(), [3]);
    assert.equal(t.clock.timers.size, 0);
  });

  test('every frame failing gives no preview and leaves no timers', () => {
    const t = run(new FakeLoader(() => false).load);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 3 * FRAME_INTERVAL_MS);
    assert.deepEqual(t.shown, []);
    assert.equal(t.noPreview(), 1);
    assert.equal(t.clock.timers.size, 0);
    t.cycle.stop();
    assert.equal(t.restored(), 0, 'nothing was shown, so nothing to restore');
  });

  test('placeholder-width frames count as failed through imageFrameLoader', () => {
    const t = run(fakeImageLoader(() => 120).loader);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS);
    assert.deepEqual(t.shown, []);
    assert.equal(t.noPreview(), 1);
  });

  test('stop before FRAME_LOAD_AT_MS requests nothing and restores nothing', () => {
    const loader = new FakeLoader(() => true);
    const t = run(loader.load);
    t.clock.advanceTo(FRAME_LOAD_AT_MS - 1);
    t.cycle.stop();
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 3 * FRAME_INTERVAL_MS);
    assert.deepEqual(loader.requests, []);
    assert.deepEqual(t.shown, []);
    assert.equal(t.restored(), 0);
    assert.equal(t.clock.timers.size, 0);
  });

  test('stop while cycling restores once, shows no more frames and clears timers', () => {
    const t = run(new FakeLoader(() => true).load);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS);
    t.cycle.stop();
    t.cycle.stop();
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 5 * FRAME_INTERVAL_MS);
    assert.deepEqual(t.frames(), [1, 2]);
    assert.equal(t.restored(), 1);
    assert.equal(t.clock.timers.size, 0);
  });

  test('stop called from inside onFrame schedules nothing more', () => {
    const clock = new FakeClock();
    const frames: number[] = [];
    const cycle = startFrameCycle({
      urls: URLS,
      clock,
      load: new FakeLoader(() => true).load,
      onFrame: (frame) => {
        frames.push(frame);
        cycle.stop();
      },
    });
    clock.advanceTo(FRAME_FIRST_AT_MS + 3 * FRAME_INTERVAL_MS);
    assert.deepEqual(frames, [1]);
    assert.equal(clock.timers.size, 0);
  });

  test('a load that finishes after stop shows nothing', () => {
    const loader = new FakeLoader();
    const t = run(loader.load);
    t.clock.advanceTo(FRAME_FIRST_AT_MS);
    t.cycle.stop();
    for (const url of URLS) loader.resolve(url, true);
    t.clock.advanceTo(FRAME_FIRST_AT_MS + 3 * FRAME_INTERVAL_MS);
    assert.deepEqual(t.shown, []);
    assert.equal(t.restored(), 0);
  });

  test('second hover through the cache: no new requests, first frame at exactly FRAME_FIRST_AT_MS', () => {
    const network = new FakeLoader();
    const cached = createFrameCache(network.load);
    const first = run(cached);
    first.clock.advanceTo(FRAME_LOAD_AT_MS);
    for (const url of URLS) network.resolve(url, true);
    first.clock.advanceTo(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS);
    first.cycle.stop();
    assert.equal(network.requests.length, 3);

    const second = run(cached);
    second.clock.advanceTo(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS);
    assert.equal(network.requests.length, 3);
    assert.deepEqual(second.shown, [
      { frame: 1, at: FRAME_FIRST_AT_MS },
      { frame: 2, at: FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS },
    ]);
  });
});

describe('createFrameCache', () => {
  test('callers asking while a load is in flight share it and all get the result', () => {
    const network = new FakeLoader();
    const cached = createFrameCache(network.load);
    const results: boolean[] = [];
    cached(URLS[0], (ok) => results.push(ok));
    cached(URLS[0], (ok) => results.push(ok));
    assert.equal(network.requests.length, 1);
    network.resolve(URLS[0], false);
    cached(URLS[0], (ok) => results.push(ok));
    assert.deepEqual(results, [false, false, false]);
    assert.equal(network.requests.length, 1);
  });

  test('stopping a cycle drops its waiters, and the shared load still reaches other callers', () => {
    const network = new FakeLoader();
    const cached = createFrameCache(network.load);
    let cycleCalls = 0;
    const counting: FrameLoader = (url, done) => cached(url, (ok) => { cycleCalls++; done(ok); });
    const stopped = run(counting);
    stopped.clock.advanceTo(FRAME_LOAD_AT_MS);
    const results: boolean[] = [];
    cached(URLS[0], (ok) => results.push(ok));
    stopped.cycle.stop();
    for (const url of URLS) network.resolve(url, true);
    assert.equal(cycleCalls, 0);
    assert.deepEqual(results, [true]);
    assert.equal(network.requests.length, 3);
  });

  test('a loader that answers synchronously still reaches the first caller', () => {
    const cached = createFrameCache(new FakeLoader(() => true).load);
    let got: boolean | null = null;
    cached(URLS[0], (ok) => (got = ok));
    assert.equal(got, true);
  });
});

/** Stands in for Image(): records the referrer policy at the moment src is set. */
function fakeImageLoader(width: () => number, fail = false) {
  const policiesAtSrc: string[] = [];
  const loader = imageFrameLoader(() => {
    const img = {
      referrerPolicy: '',
      naturalWidth: 0,
      onload: null as null | (() => void),
      onerror: null as null | (() => void),
      set src(_url: string) {
        policiesAtSrc.push(img.referrerPolicy);
        if (fail) {
          img.onerror?.();
        } else {
          img.naturalWidth = width();
          img.onload?.();
        }
      },
    };
    return img as unknown as HTMLImageElement;
  });
  return { loader, policiesAtSrc };
}

describe('imageFrameLoader', () => {
  test('sets no-referrer before src, so the request never carries a referrer', () => {
    const { loader, policiesAtSrc } = fakeImageLoader(() => 640);
    loader(URLS[0], () => {});
    assert.deepEqual(policiesAtSrc, ['no-referrer']);
  });

  test('a real-width frame is usable; the 120px placeholder and an error are not', () => {
    const results: boolean[] = [];
    fakeImageLoader(() => 640).loader(URLS[0], (ok) => results.push(ok));
    fakeImageLoader(() => 120).loader(URLS[0], (ok) => results.push(ok));
    fakeImageLoader(() => 640, true).loader(URLS[0], (ok) => results.push(ok));
    assert.deepEqual(results, [true, false, false]);
  });
});

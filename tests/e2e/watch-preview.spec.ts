// Hover previews: the On/Off switch and frame cycling on cards (UI spec
// § 4.4, § 4.5). page.clock drives the timings; frame images still arrive
// over the routed network in real time, so each test waits for them before
// stepping the clock past a frame change.
import type { Locator, Page } from '@playwright/test';
import { MQ_FINE_POINTER, PREVIEWS_STORAGE_KEY } from '../../src/lib/watch/contract';
import { frameUrls } from '../../src/lib/watch/frames';
import { FRAME_FIRST_AT_MS, FRAME_INTERVAL_MS, FRAME_LOAD_AT_MS } from '../../src/lib/watch/timings';
import { expect, isFrameUrl, test, type NetworkLog } from './helpers';

const T0 = new Date('2026-01-05T10:00:00Z').getTime();
let pausedAt = T0;

/** Opens /watch with the clock paused, so only runFor moves page time. */
async function openWatch(page: Page): Promise<Locator> {
  await page.clock.install({ time: T0 });
  pausedAt = T0;
  await page.goto('/watch');
  return settle(page);
}

async function settle(page: Page): Promise<Locator> {
  // main.ts has run once the URL names the default tab.
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
  pausedAt += 60_000;
  await page.clock.pauseAt(pausedAt);
  return page.getByTestId('watch-page');
}

function card(root: Locator, id: string): Locator {
  return root.locator(`[data-testid="watch-thumb"][data-video-id="${id}"]`);
}

async function pointAt(page: Page, target: Locator): Promise<void> {
  const media = target.locator('.watch-thumb__media');
  await media.scrollIntoViewIfNeeded();
  const box = await media.boundingBox();
  if (!box) throw new Error('card has no box');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
}

async function pointAway(page: Page): Promise<void> {
  await page.mouse.move(2, 2);
}

function frameRequests(network: NetworkLog, id?: string): string[] {
  const frames = network.requests.filter(isFrameUrl).filter((url) => !id || url.includes(`/vi/${id}/`));
  return [...new Set(frames)].sort();
}

/**
 * Steps to FRAME_LOAD_AT_MS and waits until every frame response is in.
 * The short real-time pause lets the image load events run, since the
 * cycler skips a frame that is still loading when its turn comes.
 */
async function loadFrames(page: Page, urls: readonly string[]): Promise<void> {
  const finished = Promise.all(
    urls.map((url) => page.waitForEvent('requestfinished', { predicate: (request) => request.url() === url })),
  );
  await page.clock.runFor(FRAME_LOAD_AT_MS);
  await finished;
  await page.waitForTimeout(100);
}

async function expectRestored(target: Locator): Promise<void> {
  await expect(target).not.toHaveAttribute('data-previewing');
  await expect(target).not.toHaveAttribute('data-frame');
  await expect(target.locator('img.watch-thumb__frame.is-shown')).toHaveCount(0);
}

function switchRadio(root: Locator, name: 'On' | 'Off'): Locator {
  return root.getByRole('radiogroup', { name: 'Hover previews' }).getByRole('radio', { name, exact: true });
}

async function storedPreviews(page: Page): Promise<string | null> {
  return page.evaluate((key) => localStorage.getItem(key), PREVIEWS_STORAGE_KEY);
}

test.describe('on a mouse device', () => {
  test('E3: an sd card cycles its sd frames 1, 2, 3 and leaving restores the cover', async ({ page, network }) => {
    const referers: Promise<string | undefined>[] = [];
    const localReferers: Promise<string | undefined>[] = [];
    page.on('request', (request) => {
      const referer = request.allHeaders().then((headers) => headers.referer);
      if (isFrameUrl(request.url())) referers.push(referer);
      else if (request.url().endsWith('.js')) localReferers.push(referer);
    });
    const root = await openWatch(page);
    const sd = card(root, 'fxAlpha0001');
    await expect(sd).toHaveAttribute('data-frame-tier', 'sd');
    const urls = frameUrls('fxAlpha0001', 'sd');

    await pointAt(page, sd);
    await page.clock.runFor(FRAME_LOAD_AT_MS - 1);
    expect(frameRequests(network)).toEqual([]);
    const finished = Promise.all(urls.map((url) => page.waitForEvent('requestfinished', { predicate: (r) => r.url() === url })));
    await page.clock.runFor(1);
    await finished;
    await page.waitForTimeout(100);
    expect(frameRequests(network)).toEqual([...urls].sort());

    await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
    await expect(sd).toHaveAttribute('data-previewing', 'true');
    await expect(sd).toHaveAttribute('data-frame', '1');
    const layers = sd.locator('img.watch-thumb__frame');
    await expect(layers).toHaveCount(2);
    for (const layer of await layers.all()) {
      await expect(layer).toHaveAttribute('referrerpolicy', 'no-referrer');
      await expect(layer).toHaveAttribute('alt', '');
    }
    await expect(sd.locator('img.watch-thumb__frame.is-shown')).toHaveAttribute('src', urls[0]);

    for (const frame of ['2', '3', '1']) {
      await page.clock.runFor(FRAME_INTERVAL_MS);
      await expect(sd).toHaveAttribute('data-frame', frame);
    }

    await pointAway(page);
    await expectRestored(sd);

    // Preloads and layers send no referrer; the page's own scripts prove the check can see one.
    expect(await Promise.all(referers)).toEqual(referers.map(() => undefined));
    expect((await Promise.all(localReferers)).some(Boolean)).toBe(true);
  });

  test('E3: an mq card requests its mq frames', async ({ page, network }) => {
    const root = await openWatch(page);
    const mq = card(root, 'fxAlpha0002');
    await expect(mq).toHaveAttribute('data-frame-tier', 'mq');
    const urls = frameUrls('fxAlpha0002', 'mq');

    await pointAt(page, mq);
    await loadFrames(page, urls);
    expect(frameRequests(network)).toEqual([...urls].sort());
    await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
    await expect(mq).toHaveAttribute('data-frame', '1');
    await expect(mq.locator('img.watch-thumb__frame.is-shown')).toHaveAttribute('src', urls[0]);
    await page.clock.runFor(FRAME_INTERVAL_MS);
    await expect(mq).toHaveAttribute('data-frame', '2');
  });

  test('requests no frames before the first hover', async ({ page, network }) => {
    const root = await openWatch(page);
    await page.waitForLoadState('networkidle');
    await page.clock.runFor(10_000);
    expect(frameRequests(network)).toEqual([]);
    // Positive control: the same filter sees frames once a card is hovered.
    await pointAt(page, card(root, 'fxAlpha0002'));
    await loadFrames(page, frameUrls('fxAlpha0002', 'mq'));
    expect(frameRequests(network)).toHaveLength(3);
  });

  test('keyboard focus on a card cycles too, and focus leaving restores it', async ({ page }) => {
    const root = await openWatch(page);
    const first = card(root, 'fxAlpha0001');
    // The switch sits just before the panels in tab order.
    await switchRadio(root, 'On').focus();
    await page.keyboard.press('Tab');
    await expect(first).toBeFocused();
    expect(await first.evaluate((el) => el.matches(':focus-visible'))).toBe(true);

    await loadFrames(page, frameUrls('fxAlpha0001', 'sd'));
    await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
    await expect(first).toHaveAttribute('data-frame', '1');
    await page.clock.runFor(FRAME_INTERVAL_MS);
    await expect(first).toHaveAttribute('data-frame', '2');

    await page.keyboard.press('Shift+Tab');
    await expectRestored(first);
  });

  test('a missing frame is skipped', async ({ page, network }) => {
    const root = await openWatch(page);
    const target = card(root, 'fxAlpha0003');
    const urls = frameUrls('fxAlpha0003', 'mq');
    await pointAt(page, target);
    await loadFrames(page, urls);
    // The 404 frame was asked for, so skipping it is the cycler's doing.
    expect(frameRequests(network, 'fxAlpha0003')).toContain(urls[1]);

    await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
    await expect(target).toHaveAttribute('data-frame', '1');
    for (const frame of ['3', '1', '3']) {
      await page.clock.runFor(FRAME_INTERVAL_MS);
      await expect(target).toHaveAttribute('data-frame', frame);
    }
  });

  test('Escape stops the cycle while the pointer stays on the card', async ({ page }) => {
    const root = await openWatch(page);
    const target = card(root, 'fxAlpha0002');
    await pointAt(page, target);
    await loadFrames(page, frameUrls('fxAlpha0002', 'mq'));
    await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
    await expect(target).toHaveAttribute('data-frame', '1');

    await page.keyboard.press('Escape');
    await expectRestored(target);
    // Moving within the card does not undo Escape; only a new enter does.
    const box = await target.locator('.watch-thumb__media').boundingBox();
    await page.mouse.move(box!.x + 10, box!.y + 10);
    await page.clock.runFor(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS);
    await expectRestored(target);
  });

  test('the tab going hidden stops the cycle', async ({ page }) => {
    const root = await openWatch(page);
    const target = card(root, 'fxAlpha0002');
    await pointAt(page, target);
    await loadFrames(page, frameUrls('fxAlpha0002', 'mq'));
    await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
    await expect(target).toHaveAttribute('data-frame', '1');

    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expectRestored(target);
  });

  test('E4: Off stops a running cycle at once and persists across reload', async ({ page, network }) => {
    const root = await openWatch(page);
    await expect(root.getByTestId('watch-preview-switch')).toBeVisible();
    await expect(switchRadio(root, 'On')).toHaveAttribute('aria-checked', 'true');
    expect(await storedPreviews(page)).toBeNull();

    const target = card(root, 'fxAlpha0002');
    await pointAt(page, target);
    await loadFrames(page, frameUrls('fxAlpha0002', 'mq'));
    await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
    await expect(target).toHaveAttribute('data-frame', '1');

    // Keyboard, so the pointer stays on the card and only Off can stop it.
    await switchRadio(root, 'Off').focus();
    await page.keyboard.press('Space');
    await expect(switchRadio(root, 'Off')).toHaveAttribute('aria-checked', 'true');
    await expectRestored(target);
    expect(await storedPreviews(page)).toBe('off');
    await page.clock.runFor(FRAME_INTERVAL_MS * 3);
    await expectRestored(target);

    await page.reload();
    const after = await settle(page);
    await expect(switchRadio(after, 'Off')).toHaveAttribute('aria-checked', 'true');
    await expect(switchRadio(after, 'On')).toHaveAttribute('aria-checked', 'false');
    await expect(after.getByTestId('watch-preview-hint')).toBeHidden();
    expect(await storedPreviews(page)).toBe('off');

    const before = network.requests.filter(isFrameUrl).length;
    await pointAway(page);
    await pointAt(page, card(after, 'fxAlpha0001'));
    await page.clock.runFor(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS * 2);
    await expectRestored(card(after, 'fxAlpha0001'));
    expect(network.requests.filter(isFrameUrl).length).toBe(before);
  });

  test('E6: arrow keys move and select the switch radios', async ({ page }) => {
    const root = await openWatch(page);
    const on = switchRadio(root, 'On');
    const off = switchRadio(root, 'Off');

    // The group is one tab stop, landing on the checked radio.
    await root.getByRole('link', { name: 'YouTube Terms of Service' }).focus();
    await page.keyboard.press('Tab');
    await expect(on).toBeFocused();
    await expect(off).toHaveAttribute('tabindex', '-1');

    const steps: [string, Locator][] = [
      ['ArrowRight', off],
      ['ArrowRight', on],
      ['ArrowLeft', off],
      ['ArrowUp', on],
      ['ArrowDown', off],
    ];
    for (const [key, expected] of steps) {
      await page.keyboard.press(key);
      await expect(expected).toBeFocused();
      await expect(expected).toHaveAttribute('aria-checked', 'true');
      await expect(expected).toHaveAttribute('tabindex', '0');
    }
    expect(await storedPreviews(page)).toBe('off');

    await on.focus();
    await page.keyboard.press('Enter');
    await expect(on).toHaveAttribute('aria-checked', 'true');
    expect(await storedPreviews(page)).toBe('on');
    await off.focus();
    await page.keyboard.press('Space');
    await expect(off).toHaveAttribute('aria-checked', 'true');
    expect(await storedPreviews(page)).toBe('off');
  });

  test('with nothing stored the switch follows live reduce-motion changes', async ({ page }) => {
    const root = await openWatch(page);
    const on = switchRadio(root, 'On');
    const hint = root.getByTestId('watch-preview-hint');
    await expect(on).toHaveAttribute('aria-checked', 'true');
    await expect(hint).toBeHidden();

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(switchRadio(root, 'Off')).toHaveAttribute('aria-checked', 'true');
    await expect(hint).toBeVisible();
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await expect(on).toHaveAttribute('aria-checked', 'true');
    await expect(hint).toBeHidden();

    // A11yControl's Motion setting changes data-motion without a reload.
    await page.evaluate(() => (document.documentElement.dataset.motion = 'reduce'));
    await expect(switchRadio(root, 'Off')).toHaveAttribute('aria-checked', 'true');
    await expect(hint).toBeVisible();
    await page.evaluate(() => (document.documentElement.dataset.motion = 'on'));
    await expect(on).toHaveAttribute('aria-checked', 'true');
    expect(await storedPreviews(page)).toBeNull();
  });
});

async function expectReduceDefault(page: Page, network: NetworkLog): Promise<void> {
  const root = await openWatch(page);
  const hint = root.getByTestId('watch-preview-hint');
  await expect(switchRadio(root, 'Off')).toHaveAttribute('aria-checked', 'true');
  await expect(hint).toBeVisible();
  await expect(hint).toHaveText('Off because reduce motion is on.');

  const target = card(root, 'fxAlpha0002');
  await pointAt(page, target);
  await page.clock.runFor(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS);
  await expectRestored(target);
  expect(frameRequests(network)).toEqual([]);

  await switchRadio(root, 'On').click();
  await expect(switchRadio(root, 'On')).toHaveAttribute('aria-checked', 'true');
  await expect(hint).toBeHidden();
  expect(await storedPreviews(page)).toBe('on');

  await pointAt(page, target);
  await loadFrames(page, frameUrls('fxAlpha0002', 'mq'));
  await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
  await expect(target).toHaveAttribute('data-frame', '1');
  // Under a reduce setting frames swap without the crossfade.
  await expect(target.locator('img.watch-thumb__frame.is-shown')).toHaveCSS('transition-duration', '0s');
}

test.describe('with reduce motion', () => {
  test('E5: the OS setting defaults previews to Off with the hint; On then cycles', async ({ page, network }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expectReduceDefault(page, network);
  });

  test('E5: the site Motion setting (dr-motion=reduce) does the same', async ({ page, network }) => {
    await page.addInitScript(() => localStorage.setItem('dr-motion', 'reduce'));
    await expectReduceDefault(page, network);
  });
});

test.describe('on a touch device', () => {
  test.use({ hasTouch: true, isMobile: true });

  test('the switch stays hidden', async ({ page }) => {
    const root = await openWatch(page);
    expect(await page.evaluate((query) => matchMedia(query).matches, MQ_FINE_POINTER)).toBe(false);
    await expect(root.getByTestId('watch-preview-switch')).toBeHidden();
  });
});

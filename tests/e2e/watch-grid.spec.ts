// Cards and the hover popup against the fixture build. The player is another
// component's job, so nothing here asserts an iframe; the card-to-player flow
// is covered by the cross-component spec. Timers run on page.clock, paused
// after load, so each delay is stepped exactly.
import type { Locator, Page } from '@playwright/test';
import { MQ_FINE_POINTER } from '../../src/lib/watch/contract';
import { POPUP_CLOSE_DELAY_MS, POPUP_OPEN_DELAY_MS } from '../../src/lib/watch/timings';
import { expect, test } from './helpers';

interface Box {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

async function openWatch(page: Page, path = '/watch'): Promise<void> {
  await page.clock.install();
  await page.goto(path);
  // client/main.ts has run once the URL carries the tab.
  await expect(page).toHaveURL(/[?&]list=/);
  await page.clock.pauseAt(new Date(Date.now() + 60_000));
}

function card(page: Page, id: string, slug = 'alpha'): Locator {
  return page.getByTestId('watch-page').locator(`[data-testid="watch-thumb"][data-playlist="${slug}"][data-video-id="${id}"]`);
}

function popupOf(page: Page): Locator {
  return page.getByTestId('watch-page').getByTestId('watch-popup');
}

async function rect(locator: Locator): Promise<Box> {
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { top: r.top, right: r.right, bottom: r.bottom, left: r.left };
  });
}

/** Scrolls without smooth behaviour and waits for the scroll event, so it cannot land mid-test. */
async function scrollToY(page: Page, top: number): Promise<void> {
  await page.evaluate(
    (y) =>
      new Promise<void>((resolve) => {
        if (Math.round(window.scrollY) === Math.round(y)) return resolve();
        window.addEventListener('scroll', () => resolve(), { once: true });
        window.scrollTo({ top: y, behavior: 'instant' });
      }),
    top,
  );
}

/** Brings the card into view first: hover() would scroll it and the late scroll event could interleave. */
async function restOn(page: Page, target: Locator): Promise<void> {
  const box = await rect(target);
  if (box.top < 0 || box.bottom > (page.viewportSize()?.height ?? 0)) {
    await scrollToY(page, (await page.evaluate(() => window.scrollY)) + box.top - 80);
  }
  await target.hover();
}

async function isFocusVisible(target: Locator): Promise<boolean> {
  return target.evaluate((el) => el.matches(':focus-visible'));
}

test.describe('hover popup', () => {
  test('opens after the rest delay, beside the card, with its details', async ({ page }) => {
    await openWatch(page);
    const first = card(page, 'fxAlpha0001');
    const popup = popupOf(page);
    await restOn(page, first);

    await page.clock.runFor(POPUP_OPEN_DELAY_MS - 1);
    await expect(popup).toBeHidden();
    await page.clock.runFor(1);
    await expect(popup).toBeVisible();
    await expect(popup).toHaveAttribute('data-video-id', 'fxAlpha0001');
    await expect(popup).toHaveAttribute('aria-hidden', 'true');
    const title = await first.getByTestId('watch-thumb-title').textContent();
    await expect(popup.locator('.watch-popup__title')).toHaveText(title ?? '');

    // Left-column card: right of it, touching (UI spec § 4.3 rule 1).
    const cardBox = await rect(first);
    const popupBox = await rect(popup);
    expect(Math.abs(popupBox.left - cardBox.right)).toBeLessThanOrEqual(1);
  });

  test('swaps at once to another card while open', async ({ page }) => {
    await openWatch(page);
    const first = card(page, 'fxAlpha0001');
    const third = card(page, 'fxAlpha0003');
    const popup = popupOf(page);
    // Third sits under the first, so the straight path down avoids the popup.
    await scrollToY(page, (await page.evaluate(() => window.scrollY)) + (await rect(first)).top - 20);
    await first.hover();
    await page.clock.runFor(POPUP_OPEN_DELAY_MS);
    await expect(popup).toHaveAttribute('data-video-id', 'fxAlpha0001');

    const box = await rect(third);
    await page.mouse.move(box.left + 40, box.top + 40, { steps: 5 });
    await expect(popup).toBeVisible();
    await expect(popup).toHaveAttribute('data-video-id', 'fxAlpha0003');
  });

  test('stays open while the pointer moves from card into popup, then closes after leaving both', async ({ page }) => {
    await openWatch(page);
    const first = card(page, 'fxAlpha0001');
    const popup = popupOf(page);
    await restOn(page, first);
    await page.clock.runFor(POPUP_OPEN_DELAY_MS);
    await expect(popup).toBeVisible();

    const cardBox = await rect(first);
    const popupBox = await rect(popup);
    const y = popupBox.top + 12;
    await page.mouse.move(cardBox.right - 4, y, { steps: 4 });
    await page.mouse.move(popupBox.left + 24, y, { steps: 4 });
    await page.clock.runFor(POPUP_CLOSE_DELAY_MS * 3);
    await expect(popup).toBeVisible();

    // Positive control: leaving both zones does close it, on the close delay.
    await page.mouse.move(2, 2);
    await page.clock.runFor(POPUP_CLOSE_DELAY_MS - 1);
    await expect(popup).toBeVisible();
    await page.clock.runFor(1);
    await expect(popup).toBeHidden();
  });

  test('scrolling closes it', async ({ page }) => {
    await openWatch(page);
    const popup = popupOf(page);
    await restOn(page, card(page, 'fxAlpha0001'));
    await page.clock.runFor(POPUP_OPEN_DELAY_MS);
    await expect(popup).toBeVisible();

    await page.mouse.wheel(0, 120);
    await expect(popup).toBeHidden();
  });

  test('clicking a card closes it', async ({ page }) => {
    await openWatch(page);
    const first = card(page, 'fxAlpha0001');
    const popup = popupOf(page);
    await restOn(page, first);
    await page.clock.runFor(POPUP_OPEN_DELAY_MS);
    await expect(popup).toBeVisible();

    await page.mouse.down();
    await page.mouse.up();
    await expect(popup).toBeHidden();
    await expect(first).toHaveAttribute('aria-current', 'true');
  });
});

test.describe('keyboard popup', () => {
  test('opens at once on keyboard focus, including a card scrolled into view', async ({ page }) => {
    await openWatch(page);
    const popup = popupOf(page);
    await card(page, 'fxAlpha0001').focus();

    await page.keyboard.press('Tab');
    const second = card(page, 'fxAlpha0002');
    await expect(second).toBeFocused();
    expect(await isFocusVisible(second)).toBe(true);
    await expect(popup).toBeVisible();
    await expect(popup).toHaveAttribute('data-video-id', 'fxAlpha0002');

    // The third card is on the next row; focusing it scrolls the page, and
    // that scroll must not close the popup it opened.
    await page.keyboard.press('Tab');
    await expect(card(page, 'fxAlpha0003')).toBeFocused();
    await expect(popup).toHaveAttribute('data-video-id', 'fxAlpha0003');
    // Real time, not the paused page clock: lets the late scroll event arrive.
    await page.waitForTimeout(200);
    await expect(popup).toBeVisible();
  });

  test('Escape closes it and leaves focus on the card', async ({ page }) => {
    await openWatch(page);
    const popup = popupOf(page);
    await card(page, 'fxAlpha0001').focus();
    await page.keyboard.press('Tab');
    const second = card(page, 'fxAlpha0002');
    await expect(popup).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(popup).toBeHidden();
    await expect(second).toBeFocused();
  });

  test('focus leaving the card closes it', async ({ page }) => {
    await openWatch(page);
    const popup = popupOf(page);
    // First row already in view, so focusing scrolls nothing and only the
    // blur below can close the popup.
    const first = card(page, 'fxAlpha0001');
    await scrollToY(page, (await page.evaluate(() => window.scrollY)) + (await rect(first)).top - 80);
    await first.focus();
    await page.keyboard.press('Tab');
    const second = card(page, 'fxAlpha0002');
    await expect(second).toBeFocused();
    await expect(popup).toBeVisible();

    // blur() moves focus without scrolling, unlike tabbing out of the grid.
    await second.evaluate((el) => (el as HTMLElement).blur());
    await expect(second).not.toBeFocused();
    await expect(popup).toBeHidden();
  });
});

test.describe('touch device', () => {
  test.use({ hasTouch: true, isMobile: true });

  test('shows no popup, and a tap plays', async ({ page }) => {
    await openWatch(page);
    // Positive control: the context really reports a coarse pointer.
    expect(await page.evaluate((query) => window.matchMedia(query).matches, MQ_FINE_POINTER)).toBe(false);
    const first = card(page, 'fxAlpha0001');
    const popup = popupOf(page);

    await restOn(page, first);
    await page.clock.runFor(POPUP_OPEN_DELAY_MS * 3);
    await expect(popup).toBeHidden();

    await first.focus();
    await page.keyboard.press('Tab');
    await expect(card(page, 'fxAlpha0002')).toBeFocused();
    await page.clock.runFor(POPUP_OPEN_DELAY_MS * 3);
    await expect(popup).toBeHidden();

    await first.tap();
    await expect(first).toHaveAttribute('aria-current', 'true');
    await expect(popup).toBeHidden();
  });
});

// E8: the popup never covers the player box. First-row cards are the ones
// closest to it; sweep them through the viewport, with the player in view.
for (const viewport of [
  { width: 1280, height: 720 },
  { width: 900, height: 600 },
  { width: 600, height: 800 },
]) {
  test(`E8: first-row popups never intersect the player at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await openWatch(page);
    const popup = popupOf(page);
    const frame = page.getByTestId('watch-page').getByTestId('watch-player-frame');
    const firstRow = [card(page, 'fxAlpha0001'), card(page, 'fxAlpha0002')];
    // One column at 640px and down, so only the first card is in the first row.
    const cards = viewport.width <= 640 ? firstRow.slice(0, 1) : firstRow;
    let checked = 0;

    for (const target of cards) {
      const docTop = (await rect(target)).top + (await page.evaluate(() => window.scrollY));
      const frameDocBottom = (await rect(frame)).bottom + (await page.evaluate(() => window.scrollY));
      // Card top from near the top of the viewport to near its bottom, while
      // the player's bottom edge is still on screen. The bottom 100px are
      // left out: the site's fixed display-settings button sits there.
      for (let cardTop = 40; cardTop <= viewport.height - 100; cardTop += 60) {
        const scrollY = docTop - cardTop;
        if (scrollY < 0 || frameDocBottom - scrollY <= 0) continue;
        await page.mouse.move(2, 2);
        await page.clock.runFor(POPUP_CLOSE_DELAY_MS);
        await scrollToY(page, scrollY);
        const box = await rect(target);
        await page.mouse.move((box.left + box.right) / 2, box.top + 10);
        await page.clock.runFor(POPUP_OPEN_DELAY_MS);
        await expect(popup, `card top at ${cardTop}px`).toBeVisible();

        const p = await rect(popup);
        const f = await rect(frame);
        expect(f.bottom, 'player bottom edge is in the viewport').toBeGreaterThan(0);
        const overlaps = p.left < f.right && p.right > f.left && p.top < f.bottom && p.bottom > f.top;
        expect(overlaps, `popup ${JSON.stringify(p)} vs player ${JSON.stringify(f)}`).toBe(false);
        checked += 1;
      }
    }
    expect(checked).toBeGreaterThan(2);
    await expect(page.locator('iframe')).toHaveCount(0);
  });
}

test.describe('selecting a video', () => {
  test('a click or Enter plays in the page, updates ?v= and marks one card', async ({ page }) => {
    await openWatch(page);
    const root = page.getByTestId('watch-page');
    const second = card(page, 'fxAlpha0002');
    const third = card(page, 'fxAlpha0003');
    await expect(root.locator('[data-testid="watch-thumb"][aria-current]')).toHaveCount(0);

    await second.click();
    await expect(page).toHaveURL(/\/watch\?list=alpha&v=fxAlpha0002$/);
    await expect(second).toHaveAttribute('aria-current', 'true');
    await expect(second.getByText('Playing', { exact: true })).toBeVisible();
    await expect(root.locator('[data-testid="watch-thumb"][aria-current]')).toHaveCount(1);

    await third.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/watch\?list=alpha&v=fxAlpha0003$/);
    await expect(third).toHaveAttribute('aria-current', 'true');
    await expect(second).not.toHaveAttribute('aria-current');
    await expect(second.getByText('Playing', { exact: true })).toBeHidden();
    await expect(root.locator('[data-testid="watch-thumb"][aria-current]')).toHaveCount(1);
  });

  test('a deep-linked poster marks no card', async ({ page }) => {
    await openWatch(page, '/watch?list=alpha&v=fxAlpha0002');
    await expect(page).toHaveURL(/v=fxAlpha0002/);
    await expect(page.getByTestId('watch-page').locator('[data-testid="watch-thumb"][aria-current]')).toHaveCount(0);
  });

  test('modified and middle clicks keep the YouTube link and do not play', async ({ page }) => {
    await openWatch(page);
    // Runs after the page's own handlers (bubble phase on window): records
    // whether the page cancelled the click, then cancels it so no tab opens
    // on youtube.com, which the offline network fixture would block.
    await page.evaluate(() => {
      const seen: Array<{ type: string; prevented: boolean }> = [];
      (window as unknown as { __clicks: typeof seen }).__clicks = seen;
      for (const type of ['click', 'auxclick']) {
        window.addEventListener(type, (event) => {
          seen.push({ type, prevented: event.defaultPrevented });
          event.preventDefault();
        });
      }
    });
    const first = card(page, 'fxAlpha0001');
    // ControlOrMeta: on macOS a Control-click is a context-menu click and
    // fires no click event at all.
    for (const modifier of ['ControlOrMeta', 'Shift', 'Alt'] as const) await first.click({ modifiers: [modifier] });
    await first.click({ button: 'middle' });

    const clicks = await page.evaluate(() => (window as unknown as { __clicks: unknown[] }).__clicks);
    expect(clicks).toEqual([
      ...Array.from({ length: 3 }, () => ({ type: 'click', prevented: false })),
      { type: 'auxclick', prevented: false },
    ]);
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);
    await expect(page.getByTestId('watch-page').locator('[data-testid="watch-thumb"][aria-current]')).toHaveCount(0);
  });
});

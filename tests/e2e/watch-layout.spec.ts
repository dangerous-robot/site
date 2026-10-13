// The /watch app layout against the fixture build: the list column's
// resizer (keys and drag, clamped to LIST_WIDTH), the page filling the
// window at desktop sizes, and the stacked order on narrow screens.
import type { Page } from '@playwright/test';
import { BREAKPOINT_STACK_PX, LIST_WIDTH, TESTID } from '../../src/lib/watch/contract';
import { expect, lists, test, watchRoot } from './helpers';

function resizer(page: Page) {
  return watchRoot(page).getByTestId(TESTID.resizer);
}

function listCol(page: Page) {
  return watchRoot(page).getByTestId(TESTID.listCol);
}

async function colWidth(page: Page): Promise<number> {
  return Math.round((await listCol(page).boundingBox())?.width ?? 0);
}

async function expectWidth(page: Page, px: number): Promise<void> {
  await expect(resizer(page)).toHaveAttribute('aria-valuenow', String(px));
  expect(await colWidth(page)).toBe(px);
}

function scrollSize(page: Page) {
  return page.evaluate(() => ({ scroll: document.documentElement.scrollHeight, inner: window.innerHeight }));
}

test.describe('the resizer', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('is a focusable separator with its limits', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    const handle = resizer(page);
    await expect(handle).toHaveAttribute('role', 'separator');
    await expect(handle).toHaveAttribute('tabindex', '0');
    await expect(handle).toHaveAttribute('aria-valuemin', String(LIST_WIDTH.min));
    await expect(handle).toHaveAttribute('aria-valuemax', String(LIST_WIDTH.max));
    await expectWidth(page, LIST_WIDTH.initial);
  });

  test('arrow keys step, Shift steps further, Home and End jump, and both ends clamp', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await resizer(page).focus();
    let width: number = LIST_WIDTH.initial;

    await page.keyboard.press('ArrowRight');
    width += LIST_WIDTH.step;
    await expectWidth(page, width);
    await page.keyboard.press('Shift+ArrowRight');
    width += LIST_WIDTH.bigStep;
    await expectWidth(page, width);
    await page.keyboard.press('ArrowLeft');
    width -= LIST_WIDTH.step;
    await expectWidth(page, width);
    await page.keyboard.press('Shift+ArrowLeft');
    width -= LIST_WIDTH.bigStep;
    await expectWidth(page, width);

    await page.keyboard.press('End');
    await expectWidth(page, LIST_WIDTH.max);
    await page.keyboard.press('ArrowRight');
    await expectWidth(page, LIST_WIDTH.max);
    await page.keyboard.press('Shift+ArrowRight');
    await expectWidth(page, LIST_WIDTH.max);

    await page.keyboard.press('Home');
    await expectWidth(page, LIST_WIDTH.min);
    await page.keyboard.press('ArrowLeft');
    await expectWidth(page, LIST_WIDTH.min);
    await page.keyboard.press('Shift+ArrowLeft');
    await expectWidth(page, LIST_WIDTH.min);
  });

  test('a mouse drag resizes the column and clamps at both ends', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    const box = await resizer(page).boundingBox();
    if (!box) throw new Error('resizer has no box');
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;

    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 100, y, { steps: 5 });
    await expectWidth(page, LIST_WIDTH.initial + 100);
    await page.mouse.move(x + 1000, y, { steps: 5 });
    await expectWidth(page, LIST_WIDTH.max);
    await page.mouse.move(x - 1000, y, { steps: 5 });
    await expectWidth(page, LIST_WIDTH.min);
    await page.mouse.up();

    // Released: further moves do nothing.
    await page.mouse.move(x + 200, y, { steps: 3 });
    await expectWidth(page, LIST_WIDTH.min);
  });
});

test.describe('at 1280x800', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('the page fills the window without scrolling; the columns sit side by side', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await expect(resizer(page)).toBeVisible();
    const size = await scrollSize(page);
    expect(size.scroll).toBe(size.inner);
    const col = await listCol(page).boundingBox();
    const frame = await watchRoot(page).getByTestId(TESTID.playerFrame).boundingBox();
    expect(frame && col && frame.x).toBeGreaterThan((col?.x ?? 0) + (col?.width ?? 0) - 1);
    // The list scrolls inside its own box, which ends above the footer.
    const footer = await page.locator('footer.site-footer').boundingBox();
    const box = await lists(page).boundingBox();
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual((footer?.y ?? 0) + 1);
    await expect(page.locator('footer.site-footer')).toBeInViewport({ ratio: 1 });
  });
});

test.describe('in a window under 600px tall', () => {
  test.use({ viewport: { width: 1280, height: 500 } });

  test('the page scrolls instead of shrinking', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    const size = await scrollSize(page);
    expect(size.scroll).toBeGreaterThan(size.inner);
    expect(await page.evaluate(() => document.body.getBoundingClientRect().height)).toBeGreaterThanOrEqual(600);
  });
});

/** Just inside the stacking breakpoint. */
const STACKED = { width: BREAKPOINT_STACK_PX - 60, height: 900 };

test.describe(`at ${BREAKPOINT_STACK_PX}px wide and down`, () => {
  test.use({ viewport: STACKED });

  test('stacks the player above the switcher above the list, hides the resizer and scrolls the page', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    const root = watchRoot(page);
    await expect(resizer(page)).toBeHidden();
    const frame = await root.getByTestId(TESTID.player).boundingBox();
    const switcher = await root.getByTestId(TESTID.switcher).boundingBox();
    const list = await lists(page).boundingBox();
    if (!frame || !switcher || !list) throw new Error('missing box');
    expect(frame.y + frame.height).toBeLessThanOrEqual(switcher.y + 1);
    expect(switcher.y + switcher.height).toBeLessThanOrEqual(list.y + 1);
    // Full width, not the desktop column width.
    expect(await colWidth(page)).toBe(STACKED.width);
    const size = await scrollSize(page);
    expect(size.scroll).toBeGreaterThan(size.inner);
  });
});

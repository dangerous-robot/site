// Flows that cross client controllers against the fixture build: a card
// pick through grid.ts into player.ts, tab changes against the poster and
// URL that main.ts owns, and the popup and frame preview sharing one card
// intent. Each controller's own behaviour is in its own spec.
import type { Locator, Page } from '@playwright/test';
import { EMBED_ORIGIN, PLAYER_MIN_VISIBLE_RATIO, TESTID } from '../../src/lib/watch/contract';
import { fixturePlaylist } from '../../src/lib/watch/fixtures/expected';
import { frameUrls } from '../../src/lib/watch/frames';
import { rectsOverlap, type Rect } from '../../src/lib/watch/popup-position';
import {
  FRAME_FIRST_AT_MS,
  FRAME_INTERVAL_MS,
  FRAME_LOAD_AT_MS,
  POPUP_CLOSE_DELAY_MS,
  POPUP_OPEN_DELAY_MS,
} from '../../src/lib/watch/timings';
import { card, expect, isFrameUrl, openWatch, tab, test, testid, watchRoot, type NetworkLog } from './helpers';

// FIRST has sd frames and a duration badge, SECOND mq frames and a badge,
// THIRD no duration. Only alpha has videos; bravo is empty.
const [FIRST, SECOND, THIRD] = fixturePlaylist('alpha').videoIds;

/** Tall enough that the tabs, the player and the first row of cards are all on screen. */
const TALL = { width: 1280, height: 1600 };
/** Short enough that a card in view leaves the player mostly off screen. */
const SHORT = { width: 1280, height: 500 };

function player(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.player);
}

function embeds(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.iframe);
}

function popupOf(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.popup);
}

function playing(page: Page): Locator {
  return watchRoot(page).locator(`${testid(TESTID.thumb)}[aria-current]`);
}

function embedRequests(network: NetworkLog): string[] {
  return network.requests.filter((url) => url.startsWith(EMBED_ORIGIN));
}

function frameRequests(network: NetworkLog): string[] {
  return network.requests.filter(isFrameUrl);
}

/** Without the player's own scroll, only the test decides when the frame comes into view. */
async function stubScrollIntoView(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Element.prototype.scrollIntoView = () => {};
  });
}

async function rect(locator: Locator): Promise<Rect> {
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { top: r.top, right: r.right, bottom: r.bottom, left: r.left };
  });
}

function frameRatio(page: Page): Promise<number> {
  return watchRoot(page)
    .getByTestId(TESTID.playerFrame)
    .evaluate((el) => {
      const r = el.getBoundingClientRect();
      const w = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
      const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
      return (w * h) / (r.width * r.height);
    });
}

/** Scrolls without smooth behaviour and waits for the scroll event, so it cannot land mid-test. */
async function scrollToY(page: Page, top: number): Promise<void> {
  await page.evaluate(
    (y) =>
      new Promise<void>((resolve) => {
        if (Math.round(window.scrollY) === Math.round(Math.max(0, y))) return resolve();
        window.addEventListener('scroll', () => resolve(), { once: true });
        window.scrollTo({ top: y, behavior: 'instant' });
      }),
    top,
  );
}

/** Puts the target's top edge `offset` px below the top of the viewport. */
async function scrollTopTo(page: Page, target: Locator, offset: number): Promise<void> {
  await scrollToY(page, (await page.evaluate(() => window.scrollY)) + (await rect(target)).top - offset);
}

async function inViewport(page: Page, target: Locator): Promise<boolean> {
  const box = await rect(target);
  return box.top >= 0 && box.bottom <= (page.viewportSize()?.height ?? 0);
}

/** Rests the mouse on the middle of a card's image, which must already be on screen. */
async function pointAt(page: Page, target: Locator): Promise<void> {
  const box = await rect(target.locator('.watch-thumb__media'));
  await page.mouse.move((box.left + box.right) / 2, (box.top + box.bottom) / 2);
}

/** Steps the paused clock from the rest to the first frame, waiting for the frame responses. */
async function cycleToFirstFrame(page: Page, target: Locator, id: string, tier: 'sd' | 'mq'): Promise<void> {
  const urls = frameUrls(id, tier);
  const finished = Promise.all(
    urls.map((url) => page.waitForEvent('requestfinished', { predicate: (request) => request.url() === url })),
  );
  await page.clock.runFor(POPUP_OPEN_DELAY_MS);
  await finished;
  await page.clock.runFor(FRAME_FIRST_AT_MS - FRAME_LOAD_AT_MS);
  await expect(target).toHaveAttribute('data-frame', '1');
}

async function expectRestored(target: Locator): Promise<void> {
  await expect(target).not.toHaveAttribute('data-previewing');
  await expect(target).not.toHaveAttribute('data-frame');
  await expect(target.locator('img.watch-thumb__frame.is-shown')).toHaveCount(0);
}

/** Keeps a reference to the current embed, so a later check can tell whether it was replaced. */
async function rememberEmbed(page: Page): Promise<void> {
  await page.evaluate((sel) => {
    (window as unknown as { keptEmbed: Element | null }).keptEmbed = document.querySelector(sel);
  }, testid(TESTID.iframe));
}

async function sameEmbedAsRemembered(page: Page): Promise<boolean> {
  return page.evaluate((sel) => {
    const now = document.querySelectorAll(sel);
    const kept = (window as unknown as { keptEmbed: Element | null }).keptEmbed;
    return kept !== null && now.length === 1 && now[0] === kept;
  }, testid(TESTID.iframe));
}

test.describe('picking a card with the player half in view', () => {
  test.use({ viewport: TALL });

  test('inserts exactly one embed in the same task as the click', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    const second = card(page, SECOND);
    expect(await frameRatio(page)).toBeGreaterThanOrEqual(PLAYER_MIN_VISIBLE_RATIO);
    expect(await inViewport(page, second)).toBe(true);

    // Counted inside the click's own task: an embed that waited for an
    // observer report or a timer would not be there yet.
    const inserted = await second.evaluate((el, sel) => {
      (el as HTMLElement).click();
      return [...document.querySelectorAll(sel)].map((frame) => frame.getAttribute('src'));
    }, testid(TESTID.iframe));
    expect(inserted).toHaveLength(1);
    expect(inserted[0]).toContain(`/embed/${SECOND}?`);

    await expect(embeds(page)).toHaveCount(1);
    await expect(page.locator('iframe')).toHaveCount(1);
    await expect(second).toHaveAttribute('aria-current', 'true');
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
  });

  test('Back to video list focuses the playing card', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    // Not the first card: with nothing playing, the first card gets focus anyway.
    const second = card(page, SECOND);
    await second.click();
    await expect(second).toHaveAttribute('aria-current', 'true');
    await expect(embeds(page)).toHaveCount(1);

    await player(page).getByRole('link', { name: 'Back to video list' }).click();
    await expect(second).toBeFocused();
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
  });

  test('poster Play marks the matching card as playing', async ({ page }) => {
    // Not the first video, for the same reason as above.
    await page.goto(`/watch?list=alpha&v=${SECOND}`);
    await expect(player(page)).toHaveAttribute('data-video-id', SECOND);
    await expect(playing(page)).toHaveCount(0);

    await player(page).getByTestId(TESTID.play).click();
    await expect(embeds(page)).toHaveCount(1);
    await expect(card(page, SECOND)).toHaveAttribute('aria-current', 'true');
    await expect(card(page, SECOND).getByText('Playing', { exact: true })).toBeVisible();
    await expect(playing(page)).toHaveCount(1);
  });
});

test.describe('picking a card far down the grid', () => {
  test.use({ viewport: SHORT });

  test('waits until the player is half in view, then inserts one embed', async ({ page, network }) => {
    await stubScrollIntoView(page);
    await page.goto('/watch?list=alpha');
    const third = card(page, THIRD);
    await scrollTopTo(page, third, 40);
    expect(await frameRatio(page)).toBeLessThan(PLAYER_MIN_VISIBLE_RATIO);

    await third.click();
    // The card is marked at once, while the player waits.
    await expect(third).toHaveAttribute('aria-current', 'true');
    // Proves something did not happen, so there is no event to wait for:
    // give a wrongly ungated embed time to appear.
    await page.waitForTimeout(300);
    await expect(page.locator('iframe')).toHaveCount(0);
    expect(embedRequests(network)).toEqual([]);
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);

    await scrollToY(page, 0);
    await expect(embeds(page)).toHaveCount(1);
    await expect(embeds(page)).toHaveAttribute('src', new RegExp(`/embed/${THIRD}\\?`));
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${THIRD}$`));
  });

  test('scrolls the player into view on its own, then inserts the embed', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    const third = card(page, THIRD);
    await scrollTopTo(page, third, 40);
    expect(await frameRatio(page)).toBeLessThan(PLAYER_MIN_VISIBLE_RATIO);

    await third.click();
    await expect(embeds(page)).toHaveCount(1);
    await expect(embeds(page)).toHaveAttribute('src', new RegExp(`/embed/${THIRD}\\?`));
    expect(await frameRatio(page)).toBeGreaterThanOrEqual(PLAYER_MIN_VISIBLE_RATIO);
  });

  // A pick moves ?v= only once its embed goes in, so the URL never names a
  // picked video that did not start.
  for (const [arrival, path, url] of [
    ['nothing loaded', '/watch?list=alpha', /\/watch\?list=alpha$/],
    ['a deep-linked poster', `/watch?list=alpha&v=${FIRST}`, new RegExp(`/watch\\?list=alpha&v=${FIRST}$`)],
  ] as const) {
    test(`a pick whose player never comes into view leaves ?v= alone (${arrival})`, async ({ page, network }) => {
      await stubScrollIntoView(page);
      await page.goto(path);
      const third = card(page, THIRD);
      await scrollTopTo(page, third, 40);
      expect(await frameRatio(page)).toBeLessThan(PLAYER_MIN_VISIBLE_RATIO);

      await third.click();
      await expect(third).toHaveAttribute('aria-current', 'true');
      // Proves something did not happen: give a wrongly early URL write or
      // embed time to appear.
      await page.waitForTimeout(300);
      await expect(page.locator('iframe')).toHaveCount(0);
      expect(embedRequests(network)).toEqual([]);
      await expect(page).toHaveURL(url);
    });
  }

  test('a tab change while a pick waits keeps its poster, then the URL names it once it plays', async ({ page }) => {
    await stubScrollIntoView(page);
    await page.goto('/watch?list=alpha');
    const third = card(page, THIRD);
    await scrollTopTo(page, third, 40);
    expect(await frameRatio(page)).toBeLessThan(PLAYER_MIN_VISIBLE_RATIO);

    await third.click();
    await expect(player(page)).toHaveAttribute('data-video-id', THIRD);
    // dispatchEvent, not click(): click() would scroll the tabs, and with
    // them the player, into view and let the pick play.
    await tab(page, 'bravo').dispatchEvent('click');
    await expect(tab(page, 'bravo')).toHaveAttribute('aria-selected', 'true');
    await expect(page).toHaveURL(/\/watch\?list=bravo$/);
    await tab(page, 'alpha').dispatchEvent('click');
    await expect(tab(page, 'alpha')).toHaveAttribute('aria-selected', 'true');
    await expect(player(page)).toHaveAttribute('data-video-id', THIRD);
    await expect(third).toHaveAttribute('aria-current', 'true');
    await expect(page.locator('iframe')).toHaveCount(0);
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);

    await scrollToY(page, 0);
    await expect(embeds(page)).toHaveAttribute('src', new RegExp(`/embed/${THIRD}\\?`));
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${THIRD}$`));
  });

  test('a second pick while the first waits gives exactly one embed, of the second video', async ({ page, network }) => {
    await stubScrollIntoView(page);
    await page.goto('/watch?list=alpha');
    const second = card(page, SECOND);
    const third = card(page, THIRD);
    await scrollTopTo(page, third, 40);
    expect(await frameRatio(page)).toBeLessThan(PLAYER_MIN_VISIBLE_RATIO);

    // dispatchEvent, not click(): click() would scroll each card into view
    // first, and the second card may sit above the viewport.
    await second.dispatchEvent('click');
    await expect(second).toHaveAttribute('aria-current', 'true');
    await third.dispatchEvent('click');
    await expect(third).toHaveAttribute('aria-current', 'true');
    expect(await frameRatio(page)).toBeLessThan(PLAYER_MIN_VISIBLE_RATIO);
    await page.waitForTimeout(300);
    await expect(page.locator('iframe')).toHaveCount(0);

    await scrollToY(page, 0);
    await expect(embeds(page)).toHaveCount(1);
    await expect(embeds(page)).toHaveAttribute('src', new RegExp(`/embed/${THIRD}\\?`));
    // A first pick that was never cancelled would add its embed on the same scroll.
    await page.waitForTimeout(300);
    await expect(page.locator('iframe')).toHaveCount(1);
    expect(embedRequests(network).some((url) => url.includes(`/embed/${SECOND}`))).toBe(false);
    await expect(playing(page)).toHaveCount(1);
  });
});

// The popup never covers the player box while a video plays in it. Same
// sweep as the first-row check in the grid spec, with an embed in place.
for (const viewport of [
  { width: 1280, height: 720 },
  { width: 900, height: 600 },
]) {
  test(`popups never cover the player with an embed in it at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await openWatch(page);
    const popup = popupOf(page);
    const frame = watchRoot(page).getByTestId(TESTID.playerFrame);
    await frame.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }));
    await player(page).getByTestId(TESTID.play).click();
    await expect(embeds(page)).toHaveCount(1);
    await rememberEmbed(page);

    let checked = 0;
    for (const target of [card(page, FIRST), card(page, SECOND)]) {
      const docTop = (await rect(target)).top + (await page.evaluate(() => window.scrollY));
      const frameDocBottom = (await rect(frame)).bottom + (await page.evaluate(() => window.scrollY));
      // The bottom 100px are left out: the site's fixed display-settings button sits there.
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
        expect(rectsOverlap(p, f), `popup ${JSON.stringify(p)} vs player ${JSON.stringify(f)}`).toBe(false);
        checked += 1;
      }
    }
    expect(checked).toBeGreaterThan(2);
    expect(await sameEmbedAsRemembered(page)).toBe(true);
  });
}

test.describe('changing the tab', () => {
  test.use({ viewport: TALL });

  test('the poster follows the tab until a video is loaded, then stays with the playing video', async ({ page }) => {
    await page.goto('/watch?list=bravo');
    await expect(player(page)).toBeHidden();

    // Nothing loaded: the poster follows to the new tab's first video.
    await tab(page, 'alpha').click();
    await expect(player(page)).toBeVisible();
    await expect(player(page)).toHaveAttribute('data-video-id', FIRST);
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);

    await card(page, SECOND).click();
    await expect(embeds(page)).toHaveCount(1);
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
    await rememberEmbed(page);

    // Loaded: neither tab change touches the player or the URL. Coming back
    // to alpha is the step that tells: a following poster would reset to FIRST.
    await tab(page, 'bravo').click();
    await expect(tab(page, 'bravo')).toHaveAttribute('aria-selected', 'true');
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
    await tab(page, 'alpha').click();
    await expect(tab(page, 'alpha')).toHaveAttribute('aria-selected', 'true');
    await expect(player(page)).toHaveAttribute('data-video-id', SECOND);
    await expect(player(page).getByTestId(TESTID.playerTitle)).toHaveText(`Fixture video ${SECOND}`);
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
    expect(await sameEmbedAsRemembered(page)).toBe(true);
  });

  test('a deep-linked video keeps its poster through tab changes', async ({ page }) => {
    await page.goto(`/watch?list=alpha&v=${THIRD}`);
    await expect(player(page)).toHaveAttribute('data-video-id', THIRD);

    await tab(page, 'bravo').click();
    await expect(tab(page, 'bravo')).toHaveAttribute('aria-selected', 'true');
    await tab(page, 'alpha').click();
    await expect(tab(page, 'alpha')).toHaveAttribute('aria-selected', 'true');
    await expect(player(page)).toHaveAttribute('data-video-id', THIRD);
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${THIRD}$`));
    await expect(page.locator('iframe')).toHaveCount(0);
  });

  test('arrow keys over the tabs change neither the URL nor the poster', async ({ page }) => {
    // Arriving on the empty playlist hides the player, so selecting alpha would show its poster.
    await page.goto('/watch?list=bravo');
    await expect(player(page)).toBeHidden();
    await tab(page, 'bravo').focus();

    for (const [key, focused] of [
      ['ArrowUp', 'alpha'],
      ['End', 'charlie'],
      ['Home', 'alpha'],
    ] as const) {
      await page.keyboard.press(key);
      await expect(tab(page, focused)).toBeFocused();
      await expect(page).toHaveURL(/\/watch\?list=bravo$/);
      await expect(player(page)).toBeHidden();
    }

    // Positive control: Enter on the focused alpha tab does bring its poster.
    await page.keyboard.press('Enter');
    await expect(player(page)).toHaveAttribute('data-video-id', FIRST);
    await expect(player(page)).toBeVisible();
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);
  });

  test('closes an open popup and stops frame cycling', async ({ page }) => {
    await openWatch(page);
    const first = card(page, FIRST);
    const bravo = tab(page, 'bravo');
    expect(await inViewport(page, first)).toBe(true);
    expect(await inViewport(page, bravo)).toBe(true);

    await pointAt(page, first);
    await cycleToFirstFrame(page, first, FIRST, 'sd');
    await expect(popupOf(page)).toBeVisible();

    // Focus and Enter, so the mouse stays where it is and nothing scrolls.
    await bravo.focus();
    await page.keyboard.press('Enter');
    await expect(bravo).toHaveAttribute('aria-selected', 'true');
    await expect(popupOf(page)).toBeHidden();
    await expectRestored(first);
    await page.clock.runFor(FRAME_INTERVAL_MS * 3);
    await expectRestored(first);
  });
});

test.describe('the popup and the frame preview together', () => {
  test.use({ viewport: TALL });

  test('the popup opens and frame requests start at the same rest moment', async ({ page, network }) => {
    await openWatch(page);
    const second = card(page, SECOND);
    const popup = popupOf(page);
    expect(await inViewport(page, second)).toBe(true);
    await page.waitForLoadState('networkidle');

    // A move inside the card restarts the rest for both.
    const box = await rect(second.locator('.watch-thumb__media'));
    await page.mouse.move(box.left + 40, box.top + 40);
    await page.clock.runFor(POPUP_OPEN_DELAY_MS - 100);
    await page.mouse.move(box.left + 60, box.top + 50);
    await page.clock.runFor(POPUP_OPEN_DELAY_MS - 1);
    // Give a wrongly early request time to reach the network log.
    await page.waitForTimeout(150);
    await expect(popup).toBeHidden();
    expect(frameRequests(network)).toEqual([]);

    await page.clock.runFor(1);
    await expect(popup).toBeVisible();
    await expect(popup).toHaveAttribute('data-video-id', SECOND);
    await expect.poll(() => [...new Set(frameRequests(network))].sort()).toEqual([...frameUrls(SECOND, 'mq')].sort());
  });

  test('the duration badge stays above the frame layers', async ({ page }) => {
    await openWatch(page);
    const first = card(page, FIRST);
    const badge = first.getByTestId(TESTID.thumbDuration);
    await expect(badge).toHaveCount(1);

    await pointAt(page, first);
    await cycleToFirstFrame(page, first, FIRST, 'sd');
    // Frame 2 goes on the other layer, so both layers are checked.
    for (const frame of ['1', '2']) {
      if (frame === '2') await page.clock.runFor(FRAME_INTERVAL_MS);
      await expect(first).toHaveAttribute('data-frame', frame);
      const onTop = await badge.evaluate((el) => {
        const r = el.getBoundingClientRect();
        const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
        return hit !== null && el.contains(hit);
      });
      expect(onTop, `badge on top at frame ${frame}`).toBe(true);
    }
  });

  test.describe('with the player out of view', () => {
    test.use({ viewport: SHORT });

    test('a card click mid-cycle stops the cycle and picks the video', async ({ page }) => {
      // The player would scroll itself into view and move the card from under the pointer.
      await stubScrollIntoView(page);
      await openWatch(page);
      const first = card(page, FIRST);
      await scrollTopTo(page, first, 40);
      await pointAt(page, first);
      await cycleToFirstFrame(page, first, FIRST, 'sd');

      await page.mouse.down();
      await page.mouse.up();
      await expectRestored(first);
      await expect(first).toHaveAttribute('aria-current', 'true');
      // The player is out of view and cannot scroll itself, so nothing has loaded.
      await expect(page).toHaveURL(/\/watch\?list=alpha$/);
      // The pointer is still on the card; only a new enter would restart it.
      await page.clock.runFor(FRAME_FIRST_AT_MS + FRAME_INTERVAL_MS * 2);
      await expectRestored(first);
    });
  });
});

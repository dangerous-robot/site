// Flows that cross client controllers against the fixture build: a row pick
// through list.ts into player.ts and its autoplay gate, and playlist
// switches against the player and URL that main.ts owns. Each controller's
// own behaviour is in its own spec.
import type { Locator, Page } from '@playwright/test';
import { EMBED_ORIGIN, PLAYER_MIN_VISIBLE_RATIO, TESTID } from '../../src/lib/watch/contract';
import { fixturePlaylist } from '../../src/lib/watch/fixtures/expected';
import {
  card,
  currentRows,
  expect,
  option,
  panel,
  pickPlaylist,
  player,
  playlistName,
  test,
  testid,
  watchRoot,
  type NetworkLog,
} from './helpers';

// Only alpha has videos; bravo is empty.
const [FIRST, SECOND, THIRD] = fixturePlaylist('alpha').videoIds;

/** Side by side: the player and every row are on screen and the page does not scroll. */
const WIDE = { width: 1280, height: 800 };
/** Stacked, short enough that a row in view leaves the player mostly off screen. */
const STACKED_SHORT = { width: 800, height: 500 };

function embeds(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.iframe);
}

function embedRequests(network: NetworkLog): string[] {
  return network.requests.filter((url) => url.startsWith(EMBED_ORIGIN));
}

/** Without the player's own scroll, only the test decides when the frame comes into view. */
async function stubScrollIntoView(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Element.prototype.scrollIntoView = () => {};
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
  const top = await target.evaluate((el) => el.getBoundingClientRect().top);
  await scrollToY(page, (await page.evaluate(() => window.scrollY)) + top - offset);
}

/**
 * Opens a /watch path with the third row 40px below the top of the window,
 * which leaves the player less than half in view. The player's own scroll is
 * stubbed unless `selfScroll` is set, so only the test brings it back.
 */
async function openWithThirdRowInView(page: Page, path = '/watch?list=alpha', { selfScroll = false } = {}): Promise<Locator> {
  if (!selfScroll) await stubScrollIntoView(page);
  await page.goto(path);
  const third = card(page, THIRD);
  await scrollTopTo(page, third, 40);
  expect(await frameRatio(page)).toBeLessThan(PLAYER_MIN_VISIBLE_RATIO);
  return third;
}

/** Switches playlist without the click scrolling anything: the option's own handler runs, the menu stays closed. */
async function switchQuietly(page: Page, slug: string): Promise<void> {
  await option(page, slug).dispatchEvent('click');
  await expect(panel(page, slug)).toBeVisible();
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

test.describe('picking a row with the player in view', () => {
  test.use({ viewport: WIDE });

  test('inserts exactly one embed in the same task as the click', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    const second = card(page, SECOND);
    expect(await frameRatio(page)).toBeGreaterThanOrEqual(PLAYER_MIN_VISIBLE_RATIO);
    await expect(second).toBeInViewport();

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

  test('poster Play keeps the matching row as the one current row', async ({ page }) => {
    await page.goto(`/watch?list=alpha&v=${SECOND}`);
    await expect(player(page)).toHaveAttribute('data-video-id', SECOND);
    await expect(card(page, SECOND)).toHaveAttribute('aria-current', 'true');

    await player(page).getByTestId(TESTID.play).click();
    await expect(embeds(page)).toHaveCount(1);
    await expect(card(page, SECOND)).toHaveAttribute('aria-current', 'true');
    await expect(card(page, SECOND).getByText('Playing', { exact: true })).toBeVisible();
    await expect(currentRows(page)).toHaveCount(1);
  });
});

test.describe('picking a row with the player out of view', () => {
  test.use({ viewport: STACKED_SHORT });

  test('waits until the player is half in view, then inserts one embed', async ({ page, network }) => {
    const third = await openWithThirdRowInView(page);

    await third.click();
    // The row is marked at once, while the player waits.
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
    const third = await openWithThirdRowInView(page, '/watch?list=alpha', { selfScroll: true });

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
      const third = await openWithThirdRowInView(page, path);

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

  test('a playlist switch while a pick waits keeps its poster, then the URL names it once it plays', async ({ page }) => {
    const third = await openWithThirdRowInView(page);

    await third.click();
    await expect(player(page)).toHaveAttribute('data-video-id', THIRD);
    await switchQuietly(page, 'bravo');
    await expect(page).toHaveURL(/\/watch\?list=bravo$/);
    await switchQuietly(page, 'alpha');
    await expect(player(page)).toHaveAttribute('data-video-id', THIRD);
    await expect(third).toHaveAttribute('aria-current', 'true');
    await expect(page.locator('iframe')).toHaveCount(0);
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);

    await scrollToY(page, 0);
    await expect(embeds(page)).toHaveAttribute('src', new RegExp(`/embed/${THIRD}\\?`));
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${THIRD}$`));
  });

  test('a second pick while the first waits gives exactly one embed, of the second video', async ({ page, network }) => {
    const second = card(page, SECOND);
    const third = await openWithThirdRowInView(page);

    // dispatchEvent, not click(): click() would scroll each row into view
    // first, and the second row may sit above the viewport.
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
    await expect(currentRows(page)).toHaveCount(1);
  });
});

test.describe('switching playlists', () => {
  test.use({ viewport: WIDE });

  test('never moves the poster; ?list= follows the switch until a video is loaded', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await expect(player(page)).toHaveAttribute('data-video-id', FIRST);

    await pickPlaylist(page, 'bravo');
    await expect(page).toHaveURL(/\/watch\?list=bravo$/);
    await expect(player(page)).toBeVisible();
    await expect(player(page)).toHaveAttribute('data-video-id', FIRST);
    await expect(player(page).getByTestId(TESTID.playerFrom)).toHaveText(await playlistName(page, 'alpha'));
    await expect(card(page, FIRST)).toHaveAttribute('aria-current', 'true');
  });

  test('once a video plays, neither the player, its embed nor the URL change', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await card(page, SECOND).click();
    await expect(embeds(page)).toHaveCount(1);
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
    await rememberEmbed(page);

    await pickPlaylist(page, 'bravo');
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
    await pickPlaylist(page, 'alpha');
    await expect(player(page)).toHaveAttribute('data-video-id', SECOND);
    await expect(player(page).getByTestId(TESTID.playerTitle)).toHaveText(`Fixture video ${SECOND}`);
    await expect(card(page, SECOND)).toHaveAttribute('aria-current', 'true');
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
    expect(await sameEmbedAsRemembered(page)).toBe(true);
  });

  test('a deep-linked video keeps its poster through playlist switches', async ({ page }) => {
    await page.goto(`/watch?list=alpha&v=${THIRD}`);
    await expect(player(page)).toHaveAttribute('data-video-id', THIRD);

    await pickPlaylist(page, 'bravo');
    await pickPlaylist(page, 'alpha');
    await expect(player(page)).toHaveAttribute('data-video-id', THIRD);
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${THIRD}$`));
    await expect(page.locator('iframe')).toHaveCount(0);
  });
});

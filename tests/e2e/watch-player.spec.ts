// Player behaviour against the fixture build: deep-linked posters, the
// click-to-load embed, the autoplay gate on the poster path, sizing, Show
// more and Back to video list. Card clicks come from the grid controller and
// are covered by the cross-component flows spec.
import type { Page } from '@playwright/test';
import { NOCOOKIE, expect, test } from './helpers';

const LONG = 'fxAlpha0003'; // 500-character description
const SHORT = 'fxAlpha0001'; // two short lines

function player(page: Page) {
  return page.getByTestId('watch-page').getByTestId('watch-player');
}

function frameRatio(page: Page): Promise<number> {
  return page.getByTestId('watch-player-frame').evaluate((el) => {
    const r = el.getBoundingClientRect();
    const w = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
    const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    return (w * h) / (r.width * r.height);
  });
}

test('a deep link shows that poster and no embed (E2)', async ({ page, network }) => {
  await page.goto('/watch?list=alpha&v=fxAlpha0002');
  const p = player(page);
  await expect(p).toHaveAttribute('data-video-id', 'fxAlpha0002');
  await expect(p).toHaveAttribute('data-playlist', 'alpha');
  await expect(p.getByTestId('watch-player-title')).toHaveText('Fixture video fxAlpha0002');
  await expect(p.getByRole('button', { name: 'Play: Fixture video fxAlpha0002' })).toBeVisible();
  await expect(p.getByRole('link', { name: 'Watch on YouTube' })).toHaveAttribute(
    'href',
    'https://www.youtube.com/watch?v=fxAlpha0002&list=PLfixtureAlpha01',
  );
  await expect(p.getByTestId('watch-notice')).toBeHidden();
  // A known deep-linked v counts as loaded, so the URL keeps it.
  await expect(page).toHaveURL(/\/watch\?list=alpha&v=fxAlpha0002$/);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('iframe')).toHaveCount(0);
  expect(network.requests.filter((url) => url.startsWith(NOCOOKIE))).toEqual([]);
});

test('arrival by deep link sets the poster: v alone, and list alone (E11)', async ({ page }) => {
  await page.goto('/watch?v=fxAlpha0002');
  await expect(player(page)).toHaveAttribute('data-video-id', 'fxAlpha0002');
  await expect(page).toHaveURL(/\/watch\?list=alpha&v=fxAlpha0002$/);

  await page.goto('/watch?list=alpha');
  await expect(player(page)).toHaveAttribute('data-video-id', SHORT);
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
});

test('an unknown v shows the notice and drops v from the URL', async ({ page }) => {
  await page.goto('/watch?list=alpha&v=zzUnknown00');
  const p = player(page);
  await expect(p.getByTestId('watch-notice')).toBeVisible();
  await expect(p.getByTestId('watch-notice')).toHaveText('That video is no longer in this playlist.');
  await expect(p).toHaveAttribute('data-video-id', SHORT);
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
});

test('Play loads one nocookie embed, focuses the title and names the video in the URL (E7)', async ({ page, network }) => {
  await page.goto('/watch?list=alpha');
  await page.waitForLoadState('networkidle');
  expect(network.requests.filter((url) => url.startsWith(NOCOOKIE))).toEqual([]);

  const p = player(page);
  await p.getByRole('button', { name: /^Play: / }).click();

  const iframe = p.getByTestId('watch-iframe');
  await expect(iframe).toHaveCount(1);
  await expect(page.locator('iframe')).toHaveCount(1);
  const src = new URL((await iframe.getAttribute('src')) ?? '');
  expect(src.host).toBe('www.youtube-nocookie.com');
  expect(src.pathname).toBe(`/embed/${SHORT}`);
  expect(src.searchParams.get('autoplay')).toBe('1');
  expect(src.searchParams.get('rel')).toBe('0');
  expect(await iframe.evaluate((el) => el.hasAttribute('referrerpolicy'))).toBe(false);
  await expect(iframe).toHaveAttribute('title', 'Fixture video fxAlpha0001 (YouTube video)');
  await expect(iframe).toHaveAttribute('allow', 'autoplay; encrypted-media; picture-in-picture; fullscreen');
  await expect(iframe).toHaveAttribute('allowfullscreen', '');

  await expect(p.getByTestId('watch-play')).toBeHidden();
  await expect(p.getByTestId('watch-player-title')).toBeFocused();
  // watch:play reached the page controller: the video now counts as loaded.
  await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SHORT}$`));
  // Positive control for the empty request list above.
  await expect.poll(() => network.requests.filter((url) => url.startsWith(NOCOOKIE)).length).toBeGreaterThan(0);
});

test.describe('poster Play with the frame less than half in view', () => {
  test.use({ viewport: { width: 1280, height: 600 } });

  async function scrollFrameMostlyOut(page: Page): Promise<void> {
    await page.goto(`/watch?list=alpha`);
    await page.getByTestId('watch-player-frame').evaluate((el) => {
      const r = el.getBoundingClientRect();
      window.scrollTo({ top: window.scrollY + r.top + r.height * 0.8, behavior: 'instant' });
    });
    expect(await frameRatio(page)).toBeLessThan(0.5);
  }

  test('waits for the frame to be half in view before inserting the embed', async ({ page }) => {
    // Without the scroll the gate has to hold until the reader brings the frame back.
    await page.addInitScript(() => {
      Element.prototype.scrollIntoView = () => {};
    });
    await scrollFrameMostlyOut(page);
    // dispatchEvent, not click(): click() would scroll the poster into view first.
    await page.getByTestId('watch-play').dispatchEvent('click');
    await page.waitForTimeout(300);
    await expect(page.getByTestId('watch-iframe')).toHaveCount(0);
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);

    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await expect(page.getByTestId('watch-iframe')).toHaveCount(1);
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SHORT}$`));
  });

  test('scrolls smoothly, or instantly under either reduce setting', async ({ page }) => {
    await page.addInitScript(() => {
      const calls: (ScrollIntoViewOptions | boolean | undefined)[] = [];
      Object.assign(window, { scrollCalls: calls });
      Element.prototype.scrollIntoView = (arg) => void calls.push(arg);
    });
    const behaviours = () =>
      page.evaluate(() =>
        (window as unknown as { scrollCalls: ScrollIntoViewOptions[] }).scrollCalls.map((c) => c.behavior),
      );

    await scrollFrameMostlyOut(page);
    await page.getByTestId('watch-play').dispatchEvent('click');
    expect(await behaviours()).toEqual(['smooth']);

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await scrollFrameMostlyOut(page);
    await page.getByTestId('watch-play').dispatchEvent('click');
    expect(await behaviours()).toEqual(['auto']);

    // The site's Motion setting, without the OS setting.
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await scrollFrameMostlyOut(page);
    await page.evaluate(() => {
      document.documentElement.dataset.motion = 'reduce';
    });
    await page.getByTestId('watch-play').dispatchEvent('click');
    expect(await behaviours()).toEqual(['auto']);
  });

  test('scrolls the frame into view, then inserts the embed', async ({ page }) => {
    await scrollFrameMostlyOut(page);
    await page.getByTestId('watch-play').dispatchEvent('click');
    await expect(page.getByTestId('watch-iframe')).toHaveCount(1);
    expect(await frameRatio(page)).toBeGreaterThanOrEqual(0.5);
  });
});

test.describe('at a 320px viewport', () => {
  test.use({ viewport: { width: 320, height: 640 } });

  test('the player frame and embed are at least 200x200 (E9)', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    const frame = page.getByTestId('watch-player-frame');
    const box = await frame.boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(200);
    expect(box?.height).toBeGreaterThanOrEqual(200);

    await page.getByTestId('watch-play').click();
    const iframeBox = await page.getByTestId('watch-iframe').boundingBox();
    expect(iframeBox?.width).toBeGreaterThanOrEqual(200);
    expect(iframeBox?.height).toBeGreaterThanOrEqual(200);
  });
});

test('Show more appears only for an overflowing description and toggles (E12)', async ({ page }) => {
  await page.goto(`/watch?list=alpha&v=${SHORT}`);
  const p = player(page);
  await expect(p.getByTestId('watch-player-title')).toHaveText(`Fixture video ${SHORT}`);
  await expect(p.locator('.watch-player__more')).toBeHidden();

  await page.goto(`/watch?list=alpha&v=${LONG}`);
  const more = p.getByRole('button', { name: 'Show more' });
  await expect(more).toBeVisible();
  await expect(more).toHaveAttribute('aria-expanded', 'false');
  await expect(more).toHaveAttribute('aria-controls', 'watch-player-desc');
  const desc = p.locator('#watch-player-desc');
  const clamped = (await desc.boundingBox())?.height ?? 0;

  await more.click();
  const less = p.getByRole('button', { name: 'Show less' });
  await expect(less).toHaveAttribute('aria-expanded', 'true');
  expect((await desc.boundingBox())?.height ?? 0).toBeGreaterThan(clamped);

  await less.click();
  await expect(p.getByRole('button', { name: 'Show more' })).toHaveAttribute('aria-expanded', 'false');
  expect((await desc.boundingBox())?.height ?? 0).toBe(clamped);
});

test('Back to video list focuses the first card of the selected panel when nothing is playing (E12)', async ({ page }) => {
  await page.goto('/watch?list=alpha');
  await player(page).getByRole('link', { name: 'Back to video list' }).click();
  const first = page.locator('[data-testid="watch-panel"][data-playlist="alpha"] [data-testid="watch-thumb"]').first();
  await expect(first).toHaveAttribute('data-video-id', SHORT);
  await expect(first).toBeFocused();
  // Handled in page: no hash navigation.
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
});

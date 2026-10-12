// Page-level smoke test against the fixture build: the shell renders, nothing
// from YouTube's player or frame servers loads before the reader asks, and
// the page still works without JavaScript.
import { NOCOOKIE, YTIMG, expect, isFrameUrl, test } from './helpers';

test('loads the fixture playlists without player or frame requests', async ({ page, network }) => {
  const response = await page.goto('/watch');
  expect(response?.status()).toBe(200);
  const root = page.getByTestId('watch-page');
  await expect(root).toHaveAttribute('data-watch-mode', 'fixture');
  // client/main.ts ran: the URL names the server's default tab.
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);

  const tabSlugs = await root.getByTestId('watch-tab').evaluateAll((tabs) => tabs.map((t) => t.getAttribute('data-playlist')));
  expect(tabSlugs).toEqual(['alpha', 'bravo', 'charlie']);
  await expect(root.locator('[data-playlist="delta"]')).toHaveCount(0);

  await page.waitForLoadState('networkidle');
  await expect(page.locator('iframe')).toHaveCount(0);
  expect(network.requests.filter((url) => url.startsWith(NOCOOKIE))).toEqual([]);
  expect(network.requests.filter(isFrameUrl)).toEqual([]);
  // Positive control for the two filters above: covers do come through the route.
  expect(network.requests.some((url) => url.startsWith(`${YTIMG}/vi/`))).toBe(true);
  // Startup does not announce.
  await expect(root.getByTestId('watch-status')).toHaveText('');
});

test('a failed playlist links to YouTube from its empty state', async ({ page }) => {
  await page.goto('/watch?list=charlie');
  const root = page.getByTestId('watch-page');
  const panel = root.locator('[data-testid="watch-panel"][data-playlist="charlie"]');
  await expect(panel).toBeVisible();
  await expect(root.locator('[data-testid="watch-panel"][data-playlist="alpha"]')).toBeHidden();
  const link = panel.getByTestId('watch-empty').getByRole('link', { name: 'See the playlist on YouTube' });
  await expect(link).toHaveAttribute('href', 'https://www.youtube.com/playlist?list=PLfixtureCharlie3');
});

test.describe('without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  test('every panel shows and every card links to YouTube', async ({ page }) => {
    await page.goto('/watch');
    const root = page.getByTestId('watch-page');
    const panels = root.getByTestId('watch-panel');
    await expect(panels).toHaveCount(3);
    for (const panel of await panels.all()) await expect(panel).toBeVisible();

    const thumbs = root.getByTestId('watch-thumb');
    await expect(thumbs).not.toHaveCount(0);
    for (const thumb of await thumbs.all()) {
      await expect(thumb).toBeVisible();
      await expect(thumb).toHaveAttribute('href', /^https:\/\/www\.youtube\.com\/watch\?v=[\w-]{11}&list=PLfixtureAlpha01$/);
    }
    await expect(root.getByTestId('watch-tablist')).toBeHidden();
    await expect(root.getByTestId('watch-player')).toBeHidden();
  });
});

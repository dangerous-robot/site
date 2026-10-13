// Page-level smoke test against the fixture build: the shell renders, nothing
// from YouTube's player loads before the reader asks, and the page still
// works without JavaScript.
import { EMBED_ORIGIN, TESTID } from '../../src/lib/watch/contract';
import { FIXTURE_OMITTED_SLUGS, FIXTURE_PLAYLISTS, fixturePlaylist } from '../../src/lib/watch/fixtures/expected';
import { YTIMG_ORIGIN } from '../../src/lib/watch/images';
import { expect, panel, test, watchRoot } from './helpers';

const SLUGS = FIXTURE_PLAYLISTS.map((p) => p.slug);

test('loads the fixture playlists without player requests', async ({ page, network }) => {
  const response = await page.goto('/watch');
  expect(response?.status()).toBe(200);
  const root = watchRoot(page);
  await expect(root).toHaveAttribute('data-watch-mode', 'fixture');
  // client/main.ts ran: the URL names the server's default playlist.
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Watch' })).toHaveCount(1);

  const optionSlugs = await root.getByTestId(TESTID.option).evaluateAll((els) => els.map((e) => e.getAttribute('data-playlist')));
  expect(optionSlugs).toEqual(SLUGS);
  const panelSlugs = await root.getByTestId(TESTID.panel).evaluateAll((els) => els.map((e) => e.getAttribute('data-playlist')));
  expect(panelSlugs).toEqual(SLUGS);
  for (const slug of FIXTURE_OMITTED_SLUGS) await expect(root.locator(`[data-playlist="${slug}"]`)).toHaveCount(0);

  await page.waitForLoadState('networkidle');
  await expect(page.locator('iframe')).toHaveCount(0);
  expect(network.requests.filter((url) => url.startsWith(EMBED_ORIGIN))).toEqual([]);
  // Positive control for the filter above: covers do come through the route.
  expect(network.requests.some((url) => url.startsWith(`${YTIMG_ORIGIN}/vi/`))).toBe(true);
  // Startup does not announce.
  await expect(root.getByTestId(TESTID.status)).toHaveText('');
});

test('a failed playlist links to YouTube from its empty state', async ({ page }) => {
  const failed = FIXTURE_PLAYLISTS.find((p) => p.status === 'failed');
  if (!failed) throw new Error('the fixture has no failed playlist');
  await page.goto(`/watch?list=${failed.slug}`);
  await expect(panel(page, failed.slug)).toBeVisible();
  await expect(panel(page, 'alpha')).toBeHidden();
  const link = panel(page, failed.slug).getByTestId(TESTID.empty).getByRole('link', { name: 'See the playlist on YouTube' });
  await expect(link).toHaveAttribute('href', `https://www.youtube.com/playlist?list=${failed.youtubeId}`);
});

test.describe('without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  test('every panel shows under its heading and every row links to YouTube', async ({ page }) => {
    await page.goto('/watch');
    const root = watchRoot(page);
    const panels = root.getByTestId(TESTID.panel);
    await expect(panels).toHaveCount(FIXTURE_PLAYLISTS.length);
    for (const p of await panels.all()) {
      await expect(p).toBeVisible();
      const heading = p.getByRole('heading', { level: 2 });
      await expect(heading).toBeVisible();
      await expect(heading).not.toHaveText('');
      // The sr-only clip is undone, so the heading has a real box.
      expect((await heading.boundingBox())?.width ?? 0).toBeGreaterThan(20);
    }

    const thumbs = root.getByTestId(TESTID.thumb);
    const alpha = fixturePlaylist('alpha');
    await expect(thumbs).toHaveCount(alpha.videoIds.length);
    for (const thumb of await thumbs.all()) {
      await expect(thumb).toBeVisible();
      await expect(thumb).toHaveAttribute('href', new RegExp(`^https://www\\.youtube\\.com/watch\\?v=[\\w-]{11}&list=${alpha.youtubeId}$`));
    }
    await expect(root.getByTestId(TESTID.switcher)).toBeHidden();
    await expect(root.getByTestId(TESTID.resizer)).toBeHidden();
    await expect(root.getByTestId(TESTID.player)).toBeHidden();
    await expect(root.getByTestId(TESTID.notice)).toBeHidden();
  });
});

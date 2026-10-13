// Video rows against the fixture build: a plain click or Enter plays in the
// page, modified clicks keep the YouTube link, and exactly one row carries
// the current mark, which follows the video in the player.
import { TESTID } from '../../src/lib/watch/contract';
import { fixturePlaylist } from '../../src/lib/watch/fixtures/expected';
import { card, currentRows, expect, test, watchRoot } from './helpers';

const [FIRST, SECOND, THIRD] = fixturePlaylist('alpha').videoIds;

test('each row shows its cover, duration, title and "channel · date"', async ({ page }) => {
  await page.goto('/watch?list=alpha');
  const first = card(page, FIRST);
  await expect(first).toHaveAttribute('href', `https://www.youtube.com/watch?v=${FIRST}&list=PLfixtureAlpha01`);
  await expect(first.getByTestId(TESTID.thumbTitle)).toHaveText(`Fixture video ${FIRST}`);
  await expect(first.getByTestId(TESTID.thumbDuration)).toBeVisible();
  await expect(first.locator('.watch-thumb__meta')).toHaveText(/^.+ · .+$/);
  const media = await first.locator('.watch-thumb__media').boundingBox();
  expect(Math.round(media?.width ?? 0)).toBe(128);
  // THIRD has no duration in the fixture, so no badge.
  await expect(card(page, THIRD).getByTestId(TESTID.thumbDuration)).toHaveCount(0);
});

test('the video in the player is current from first load', async ({ page }) => {
  await page.goto('/watch?list=alpha');
  await expect(currentRows(page)).toHaveCount(1);
  await expect(card(page, FIRST)).toHaveAttribute('aria-current', 'true');
  await expect(card(page, FIRST).locator('.watch-thumb__playing')).toBeVisible();
  await expect(card(page, SECOND).locator('.watch-thumb__playing')).toBeHidden();
});

test('a deep-linked poster marks its own row', async ({ page }) => {
  await page.goto(`/watch?list=alpha&v=${SECOND}`);
  await expect(page).toHaveURL(new RegExp(`v=${SECOND}`));
  await expect(card(page, SECOND)).toHaveAttribute('aria-current', 'true');
  await expect(currentRows(page)).toHaveCount(1);
});

test('a click or Enter plays in the page, updates ?v= and moves the one mark', async ({ page }) => {
  await page.goto('/watch?list=alpha');
  const root = watchRoot(page);
  const second = card(page, SECOND);
  const third = card(page, THIRD);

  // ?v= follows the embed, not the click.
  const embed = root.getByTestId(TESTID.iframe);
  await second.click();
  await expect(embed).toHaveAttribute('src', new RegExp(`/embed/${SECOND}\\?`));
  await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
  await expect(second).toHaveAttribute('aria-current', 'true');
  await expect(second.getByText('Playing', { exact: true })).toBeVisible();
  await expect(card(page, FIRST)).not.toHaveAttribute('aria-current');
  await expect(currentRows(page)).toHaveCount(1);

  await third.focus();
  await page.keyboard.press('Enter');
  await expect(embed).toHaveAttribute('src', new RegExp(`/embed/${THIRD}\\?`));
  await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${THIRD}$`));
  await expect(third).toHaveAttribute('aria-current', 'true');
  await expect(second).not.toHaveAttribute('aria-current');
  await expect(second.getByText('Playing', { exact: true })).toBeHidden();
  await expect(currentRows(page)).toHaveCount(1);
});

test('a row keeps its height when it becomes current', async ({ page }) => {
  await page.goto('/watch?list=alpha');
  const second = card(page, SECOND);
  await expect(second).not.toHaveAttribute('aria-current');
  const before = await second.boundingBox();
  await second.click();
  await expect(second).toHaveAttribute('aria-current', 'true');
  const after = await second.boundingBox();
  expect(after?.height).toBe(before?.height);
  expect(after?.width).toBe(before?.width);
});

test('modified and middle clicks keep the YouTube link and do not play', async ({ page }) => {
  await page.goto('/watch?list=alpha');
  await expect(card(page, FIRST)).toHaveAttribute('aria-current', 'true');
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
  const second = card(page, SECOND);
  // ControlOrMeta: on macOS a Control-click is a context-menu click and
  // fires no click event at all.
  for (const modifier of ['ControlOrMeta', 'Shift', 'Alt'] as const) await second.click({ modifiers: [modifier] });
  await second.click({ button: 'middle' });

  const clicks = await page.evaluate(() => (window as unknown as { __clicks: unknown[] }).__clicks);
  expect(clicks).toEqual([
    ...Array.from({ length: 3 }, () => ({ type: 'click', prevented: false })),
    { type: 'auxclick', prevented: false },
  ]);
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
  await expect(page.locator('iframe')).toHaveCount(0);
  await expect(currentRows(page)).toHaveCount(1);
  await expect(card(page, FIRST)).toHaveAttribute('aria-current', 'true');
});

// Playlist tabs against the fixture build: selecting a tab swaps the panel,
// rewrites ?list= and announces; deep links pick the tab; the keyboard
// follows the tabs pattern with manual activation.
import type { Locator, Page } from '@playwright/test';
import { expect, test } from './helpers';

const SLUGS = ['alpha', 'bravo', 'charlie'] as const;
type Slug = (typeof SLUGS)[number];

function setup(page: Page) {
  // Base.astro renders a second role="status", so every query is scoped.
  const root = page.getByTestId('watch-page');
  const tab = (slug: Slug) => root.locator(`[data-testid="watch-tab"][data-playlist="${slug}"]`);
  const panel = (slug: Slug) => root.locator(`[data-testid="watch-panel"][data-playlist="${slug}"]`);
  const status = root.getByTestId('watch-status');
  return { root, tab, panel, status };
}

async function expectSelected(page: Page, selected: Slug, focusable: Slug = selected) {
  const { tab, panel } = setup(page);
  for (const slug of SLUGS) {
    await expect(tab(slug)).toHaveAttribute('aria-selected', slug === selected ? 'true' : 'false');
    await expect(tab(slug)).toHaveAttribute('tabindex', slug === focusable ? '0' : '-1');
    if (slug === selected) await expect(panel(slug)).toBeVisible();
    else await expect(panel(slug)).toBeHidden();
  }
}

async function tabName(tab: Locator): Promise<string> {
  return (await tab.locator('.watch-tab__name').textContent())?.trim() ?? '';
}

test('selecting a tab swaps the panel, sets ?list= and announces it', async ({ page }) => {
  await page.goto('/watch');
  const { root, tab, panel, status } = setup(page);
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
  await expectSelected(page, 'alpha');

  const bravoName = await tabName(tab('bravo'));
  expect(bravoName).not.toBe('');
  await root.getByRole('tab', { name: bravoName, exact: true }).click();
  await expectSelected(page, 'bravo');
  await expect(page).toHaveURL(/\/watch\?list=bravo$/);
  await expect(status).toHaveText(`${bravoName}, no videos to show.`);
  await expect(tab('bravo')).toBeFocused();

  const alphaName = await tabName(tab('alpha'));
  const n = await panel('alpha').getByTestId('watch-thumb').count();
  expect(n).toBeGreaterThan(1);
  // A click on the description span still selects its tab.
  await tab('alpha').locator('.watch-tab__desc').click();
  await expectSelected(page, 'alpha');
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
  await expect(status).toHaveText(`${alphaName}, ${n} videos.`);
});

test('a ?list= deep link selects that tab without announcing', async ({ page }) => {
  await page.goto('/watch?list=bravo');
  const { status } = setup(page);
  await expectSelected(page, 'bravo');
  await expect(page).toHaveURL(/\/watch\?list=bravo$/);
  await expect(status).toHaveText('');
});

test('an unknown ?list= falls back to the default tab and leaves the URL', async ({ page }) => {
  await page.goto('/watch?list=nope');
  await expectSelected(page, 'alpha');
  await expect(page).toHaveURL(/\/watch\?list=alpha$/);
  expect(page.url()).not.toContain('nope');
});

test('arrow keys, Home and End move focus only; Enter and Space select', async ({ page }) => {
  await page.goto('/watch');
  const { tab, status } = setup(page);
  await expectSelected(page, 'alpha');
  await tab('alpha').focus();
  await expect(tab('alpha')).toBeFocused();

  const press = async (key: string, focused: Slug) => {
    await page.keyboard.press(key);
    await expect(tab(focused)).toBeFocused();
    // Manual activation: selection, panel, URL and live region stay put.
    await expectSelected(page, 'alpha', focused);
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);
    await expect(status).toHaveText('');
  };

  await press('ArrowDown', 'bravo');
  await press('ArrowRight', 'charlie');
  await press('ArrowDown', 'alpha'); // wraps from last to first
  await press('ArrowUp', 'charlie'); // wraps from first to last
  await press('ArrowLeft', 'bravo');
  await press('Home', 'alpha');
  await press('End', 'charlie');

  await page.keyboard.press('Enter');
  await expectSelected(page, 'charlie');
  await expect(tab('charlie')).toBeFocused();
  await expect(page).toHaveURL(/\/watch\?list=charlie$/);
  await expect(status).toHaveText(`${await tabName(tab('charlie'))}, no videos to show.`);

  await page.keyboard.press('ArrowUp');
  await expect(tab('bravo')).toBeFocused();
  await page.keyboard.press('Space');
  await expectSelected(page, 'bravo');
  await expect(tab('bravo')).toBeFocused();
  await expect(page).toHaveURL(/\/watch\?list=bravo$/);
});

test('leaving the tab list after arrowing returns focus to the selected tab', async ({ page }) => {
  await page.goto('/watch');
  const { tab } = setup(page);
  await tab('alpha').focus();
  await page.keyboard.press('ArrowDown');
  await expect(tab('bravo')).toBeFocused();

  await page.keyboard.press('Tab');
  await expect(tab('bravo')).not.toBeFocused();
  await expectSelected(page, 'alpha');
  await page.keyboard.press('Shift+Tab');
  await expect(tab('alpha')).toBeFocused();
});

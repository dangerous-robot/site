// Playlist switcher against the fixture build: the menu (open, close, keys,
// scrim), picking a playlist (panel, "N of M", trigger card, ?list=, live
// region), each playlist's scroll position, and the now-playing line.
import type { Page } from '@playwright/test';
import { CLASS, TESTID } from '../../src/lib/watch/contract';
import { FIXTURE_PLAYLISTS, fixturePlaylist } from '../../src/lib/watch/fixtures/expected';
import { switcherPos, triggerLabel } from '../../src/lib/watch/layout';
import {
  card,
  expect,
  lists,
  menu,
  nowPlaying,
  option,
  panel,
  pickPlaylist,
  player,
  playlistName,
  test,
  trigger,
  watchRoot,
} from './helpers';

const SLUGS = FIXTURE_PLAYLISTS.map((p) => p.slug);
const [FIRST, SECOND, THIRD] = fixturePlaylist('alpha').videoIds;

function scrim(page: Page) {
  return watchRoot(page).getByTestId(TESTID.scrim);
}

function pos(page: Page) {
  return watchRoot(page).getByTestId(TESTID.switcherPos);
}

function triggerCard(page: Page, slug: string) {
  return trigger(page).locator(`.watch-switcher__card[data-playlist="${slug}"]`);
}

/** Three fixture rows do not overflow a full-height column, so the list box is made short. */
async function shortLists(page: Page): Promise<void> {
  await lists(page).evaluate((el) => {
    el.style.flex = 'none';
    el.style.height = '120px';
    el.scrollTop = 0;
  });
  expect(await lists(page).evaluate((el) => el.scrollHeight > el.clientHeight + 100)).toBe(true);
}

async function expectSelected(page: Page, selected: string): Promise<void> {
  await expect(pos(page)).toHaveText(switcherPos(SLUGS.indexOf(selected), SLUGS.length));
  await expect(trigger(page)).toHaveAttribute('aria-label', triggerLabel(await playlistName(page, selected)));
  for (const slug of SLUGS) {
    if (slug === selected) {
      await expect(panel(page, slug)).toBeVisible();
      await expect(triggerCard(page, slug)).toBeVisible();
    } else {
      await expect(panel(page, slug)).toBeHidden();
      await expect(triggerCard(page, slug)).toBeHidden();
    }
  }
}

async function expectClosed(page: Page): Promise<void> {
  await expect(menu(page)).toBeHidden();
  await expect(scrim(page)).toBeHidden();
  await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false');
}

test.describe('the menu', () => {
  test('opens over a scrim with focus on the first other playlist; Escape closes it to the trigger', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await expect(trigger(page)).toHaveAttribute('aria-controls', 'watch-menu');
    await expectClosed(page);

    await trigger(page).click();
    await expect(menu(page)).toBeVisible();
    await expect(scrim(page)).toBeVisible();
    await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    // The selected playlist is not offered.
    await expect(option(page, 'alpha')).toBeHidden();
    await expect(option(page, 'bravo')).toBeVisible();
    await expect(option(page, 'charlie')).toBeVisible();
    await expect(option(page, 'bravo')).toBeFocused();

    await page.keyboard.press('Escape');
    await expectClosed(page);
    await expect(trigger(page)).toBeFocused();
    await expectSelected(page, 'alpha');
  });

  test('a scrim click closes it and returns focus to the trigger', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await trigger(page).click();
    await expect(menu(page)).toBeVisible();

    // Below the menu, which sits over the top of the scrim.
    const menuBox = await menu(page).boundingBox();
    const scrimBox = await scrim(page).boundingBox();
    if (!menuBox || !scrimBox) throw new Error('menu or scrim has no box');
    const y = menuBox.y + menuBox.height + 40 - scrimBox.y;
    expect(y).toBeLessThan(scrimBox.height - 40);
    await scrim(page).click({ position: { x: scrimBox.width / 2, y } });
    await expectClosed(page);
    await expect(trigger(page)).toBeFocused();
    await expectSelected(page, 'alpha');
  });

  test('a second trigger click closes it', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await trigger(page).click();
    await expect(menu(page)).toBeVisible();
    await trigger(page).click();
    await expectClosed(page);
  });

  test('ArrowUp and ArrowDown move among the visible options and wrap; Enter picks', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await trigger(page).focus();
    await page.keyboard.press('Enter');
    await expect(option(page, 'bravo')).toBeFocused();

    for (const [key, focused] of [
      ['ArrowDown', 'charlie'],
      ['ArrowDown', 'bravo'], // wraps from last to first
      ['ArrowUp', 'charlie'], // wraps from first to last
      ['ArrowUp', 'bravo'],
    ] as const) {
      await page.keyboard.press(key);
      await expect(option(page, focused)).toBeFocused();
      // Moving focus picks nothing.
      await expectSelected(page, 'alpha');
      await expect(page).toHaveURL(/\/watch\?list=alpha$/);
    }

    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await expectClosed(page);
    await expect(trigger(page)).toBeFocused();
    await expectSelected(page, 'charlie');
    await expect(page).toHaveURL(/\/watch\?list=charlie$/);
  });

  test('tabbing out of the menu closes it', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await trigger(page).click();
    await expect(option(page, 'bravo')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(option(page, 'charlie')).toBeFocused();
    await expect(menu(page)).toBeVisible();
    await page.keyboard.press('Tab');
    await expectClosed(page);
    await expect(nowPlaying(page)).toBeFocused();
  });
});

test.describe('picking a playlist', () => {
  test('swaps the panel, "N of M", the trigger card and ?list=, and announces it', async ({ page }) => {
    await page.goto('/watch');
    const status = watchRoot(page).getByTestId(TESTID.status);
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);
    await expectSelected(page, 'alpha');

    await pickPlaylist(page, 'bravo');
    await expectClosed(page);
    await expect(trigger(page)).toBeFocused();
    await expectSelected(page, 'bravo');
    await expect(page).toHaveURL(/\/watch\?list=bravo$/);
    await expect(status).toHaveText(`${await playlistName(page, 'bravo')}, no videos to show.`);
    // The menu now offers alpha and charlie.
    await trigger(page).click();
    await expect(option(page, 'bravo')).toBeHidden();
    await expect(option(page, 'alpha')).toBeFocused();
    await expect(option(page, 'charlie')).toBeVisible();

    const n = fixturePlaylist('alpha').videoIds.length;
    expect(n).toBeGreaterThan(1);
    await option(page, 'alpha').click();
    await expectSelected(page, 'alpha');
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);
    await expect(status).toHaveText(`${await playlistName(page, 'alpha')}, ${n} videos.`);
  });

  test('a ?list= deep link selects that playlist without announcing', async ({ page }) => {
    await page.goto('/watch?list=bravo');
    await expectSelected(page, 'bravo');
    await expect(page).toHaveURL(/\/watch\?list=bravo$/);
    await expect(watchRoot(page).getByTestId(TESTID.status)).toHaveText('');
  });

  test('an unknown ?list= falls back to the default playlist and leaves the URL', async ({ page }) => {
    await page.goto('/watch?list=nope');
    await expectSelected(page, 'alpha');
    await expect(page).toHaveURL(/\/watch\?list=alpha$/);
    expect(page.url()).not.toContain('nope');
  });

  test('the menu option holding the video in the player shows the playing glyph', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await pickPlaylist(page, 'bravo');
    await trigger(page).click();
    await expect(option(page, 'alpha').locator(`.${CLASS.optionPlaying}`)).toBeVisible();
    await expect(option(page, 'charlie').locator(`.${CLASS.optionPlaying}`)).toBeHidden();
    await expect(option(page, 'alpha').getByRole('img', { name: 'Has the video in the player' })).toBeVisible();
  });
});

test.describe('scroll position', () => {
  test('each playlist keeps its own list scroll position', async ({ page }) => {
    await page.goto('/watch?list=alpha');
    await shortLists(page);
    const scroller = lists(page);
    await scroller.evaluate((el) => {
      el.scrollTop = 90;
    });
    await expect.poll(() => scroller.evaluate((el) => el.scrollTop)).toBe(90);

    await pickPlaylist(page, 'bravo');
    await expect.poll(() => scroller.evaluate((el) => el.scrollTop)).toBe(0);

    await pickPlaylist(page, 'alpha');
    await expect.poll(() => scroller.evaluate((el) => el.scrollTop)).toBe(90);
  });
});

test.describe('the now-playing line', () => {
  test('in the same playlist it names the video and scrolls to and focuses its row', async ({ page }) => {
    await page.goto(`/watch?list=alpha`);
    await card(page, THIRD).click();
    await expect(card(page, THIRD)).toHaveAttribute('aria-current', 'true');
    const np = nowPlaying(page);
    await expect(np).toBeEnabled();
    await expect(np).toHaveText(`Now playing: Fixture video ${THIRD}`);

    // Short box, scrolled to the top, so the third row is out of view.
    await shortLists(page);
    await expect(card(page, THIRD)).not.toBeInViewport();
    await np.click();
    await expect(card(page, THIRD)).toBeFocused();
    await expect.poll(() => lists(page).evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
    await expect(card(page, THIRD)).toBeInViewport();
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${THIRD}$`));
  });

  test('in another playlist it offers the way back, then switches and focuses the row', async ({ page }) => {
    await page.goto(`/watch?list=alpha&v=${SECOND}`);
    await pickPlaylist(page, 'bravo');
    const np = nowPlaying(page);
    const alphaName = await playlistName(page, 'alpha');
    await expect(np).toHaveText(`Back to now playing in ${alphaName}`);
    // Switching playlists never moves the player.
    await expect(player(page)).toHaveAttribute('data-video-id', SECOND);

    await np.click();
    await expectSelected(page, 'alpha');
    await expect(card(page, SECOND)).toBeFocused();
    await expect(card(page, SECOND)).toBeInViewport();
    await expect(np).toHaveText(`Now playing: Fixture video ${SECOND}`);
    await expect(page).toHaveURL(new RegExp(`/watch\\?list=alpha&v=${SECOND}$`));
  });

  test('is disabled and hidden, but keeps its place, when nothing is in the player', async ({ page }) => {
    await page.goto('/watch?list=bravo');
    const np = nowPlaying(page);
    await expect(np).toBeDisabled();
    await expect(np).toBeHidden();
    await expect(np).toHaveCSS('visibility', 'hidden');
    expect((await np.boundingBox())?.height ?? 0).toBeGreaterThan(0);
  });

  test('keeps its height and the row heights through video and playlist changes', async ({ page }) => {
    await page.goto('/watch?list=bravo');
    const np = nowPlaying(page);
    const heights = async () => ({
      np: (await np.boundingBox())?.height,
      row: (await card(page, FIRST).boundingBox())?.height ?? null,
    });

    const empty = (await np.boundingBox())?.height;
    expect(empty).toBeGreaterThan(0);

    await pickPlaylist(page, 'alpha');
    const base = await heights();
    expect(base.np).toBe(empty);
    expect(base.row).toBeGreaterThan(0);

    await card(page, FIRST).click();
    await expect(np).toHaveText(/^\s*Now playing: /);
    expect(await heights()).toEqual(base);

    await card(page, SECOND).click();
    await expect(card(page, FIRST)).not.toHaveAttribute('aria-current');
    expect(await heights()).toEqual(base);

    await pickPlaylist(page, 'charlie');
    await expect(np).toHaveText(/^\s*Back to now playing in /);
    expect((await np.boundingBox())?.height).toBe(base.np);

    await pickPlaylist(page, 'alpha');
    expect(await heights()).toEqual(base);
  });
});

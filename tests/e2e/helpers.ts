// Shared browser-test setup for /watch. Every spec imports `test` and
// `expect` from here, so each test runs offline: i.ytimg.com answers with
// generated images, youtube-nocookie.com with a blank page, and any other
// external request is blocked and fails the test at teardown.
import { test as base, expect, type Locator, type Page, type Route } from '@playwright/test';
import { deflateSync } from 'node:zlib';
import { EMBED_ORIGIN, TESTID } from '../../src/lib/watch/contract';
import { YTIMG_ORIGIN } from '../../src/lib/watch/images';

export { expect };

type TestId = (typeof TESTID)[keyof typeof TESTID];

export function testid(id: TestId): string {
  return `[data-testid="${id}"]`;
}

/** The page root. Base.astro renders a second role="status", so every query is scoped to it. */
export function watchRoot(page: Page): Locator {
  return page.getByTestId(TESTID.page);
}

/** A video row in a playlist's list. */
export function card(page: Page, id: string, slug = 'alpha'): Locator {
  return watchRoot(page).locator(`${testid(TESTID.thumb)}[data-playlist="${slug}"][data-video-id="${id}"]`);
}

/** Every row marked as holding the video in the player. */
export function currentRows(page: Page): Locator {
  return watchRoot(page).locator(`${testid(TESTID.thumb)}[aria-current="true"]`);
}

export function panel(page: Page, slug: string): Locator {
  return watchRoot(page).locator(`${testid(TESTID.panel)}[data-playlist="${slug}"]`);
}

export function trigger(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.trigger);
}

export function menu(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.menu);
}

export function option(page: Page, slug: string): Locator {
  return watchRoot(page).locator(`${testid(TESTID.option)}[data-playlist="${slug}"]`);
}

/** The status line under the switcher ("Now playing: ..." or "Back to now playing in ..."). */
export function nowPlaying(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.nowPlaying);
}

/** The scroll box holding every playlist's panel. */
export function lists(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.lists);
}

export function player(page: Page): Locator {
  return watchRoot(page).getByTestId(TESTID.player);
}

/** A playlist's display name, read from its card in the trigger (rendered for every playlist). */
export async function playlistName(page: Page, slug: string): Promise<string> {
  const name = await trigger(page).locator(`[data-playlist="${slug}"] .pl-card__name`).textContent();
  if (!name?.trim()) throw new Error(`no name rendered for playlist ${slug}`);
  return name.trim();
}

/** Opens the switcher menu and picks a playlist with real clicks. */
export async function pickPlaylist(page: Page, slug: string): Promise<void> {
  await trigger(page).click();
  await expect(menu(page)).toBeVisible();
  await option(page, slug).click();
  await expect(panel(page, slug)).toBeVisible();
}

const COVER_SIZE = [480, 270] as const;

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(bytes: Buffer): number {
  let c = 0xffffffff;
  for (const b of bytes) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

let coverPng: Buffer | undefined;

/** One solid grey 480x270 PNG, built once; the browser sniffs the type, so a .jpg URL can carry it. */
function cover(): Buffer {
  if (coverPng) return coverPng;
  const [width, height] = COVER_SIZE;
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8; // bit depth
  header[9] = 0; // greyscale
  const row = Buffer.alloc(width + 1, 128);
  row[0] = 0; // filter: none
  coverPng = Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.concat(Array.from({ length: height }, () => row)))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
  return coverPng;
}

function fulfillImage(route: Route): Promise<void> {
  return route.fulfill({ status: 200, contentType: 'image/png', body: cover() });
}

export interface NetworkLog {
  /** Every request the page made, in order, by full URL. */
  requests: string[];
  /** External requests that were blocked; the test fails if any. */
  blocked: string[];
}

interface WatchFixtures {
  network: NetworkLog;
}

export const test = base.extend<WatchFixtures>({
  network: [
    async ({ context, baseURL }, use) => {
      const local = new URL(baseURL ?? 'http://127.0.0.1').origin;
      const log: NetworkLog = { requests: [], blocked: [] };
      context.on('request', (request) => log.requests.push(request.url()));
      // Only external requests are routed, so the page's own files load
      // without a round trip through the test. One handler for all of them:
      // separate routes would need care over which registration wins.
      await context.route((url) => url.origin !== local, (route) => {
        const url = new URL(route.request().url());
        if (url.origin === YTIMG_ORIGIN) return fulfillImage(route);
        if (url.origin === EMBED_ORIGIN) {
          return route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>player</title>' });
        }
        log.blocked.push(url.href);
        return route.abort('blockedbyclient');
      });
      await use(log);
      expect(log.blocked, 'external requests outside i.ytimg.com and youtube-nocookie.com').toEqual([]);
    },
    { auto: true },
  ],
});

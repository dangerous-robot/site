// Shared browser-test setup for /watch. Every spec imports `test` and
// `expect` from here, so each test runs offline: i.ytimg.com answers with
// generated images, youtube-nocookie.com with a blank page, and any other
// external request is blocked and fails the test at teardown.
import { test as base, expect, type Route } from '@playwright/test';
import { deflateSync } from 'node:zlib';

export { expect };

export const YTIMG = 'https://i.ytimg.com';
export const NOCOOKIE = 'https://www.youtube-nocookie.com';

/** Hover-preview frames (sd1 to sd3, mq1 to mq3); covers such as mqdefault.jpg do not match. */
export const FRAME_PATH_RE = /^\/vi\/[^/]+\/(sd|mq)([1-3])\.jpg$/;

export function isFrameUrl(url: string): boolean {
  const parsed = new URL(url);
  return parsed.origin === YTIMG && FRAME_PATH_RE.test(parsed.pathname);
}

/**
 * Frame paths answered the way YouTube answers a missing frame: HTTP 404
 * with a 120x90 grey image. Override per test with test.use({ missingFrames }).
 */
export const DEFAULT_MISSING_FRAMES: readonly string[] = ['/vi/fxAlpha0003/mq2.jpg'];

const SIZES = {
  cover: [480, 270],
  sd: [640, 480],
  mq: [320, 180],
  missing: [120, 90],
} as const;

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

const pngCache = new Map<string, Buffer>();

/** A solid grey PNG; the browser sniffs the type, so a .jpg URL can carry it. */
export function solidPng(width: number, height: number, shade = 128): Buffer {
  const key = `${width}x${height}:${shade}`;
  const hit = pngCache.get(key);
  if (hit) return hit;
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8; // bit depth
  header[9] = 0; // greyscale
  const row = Buffer.alloc(width + 1, shade);
  row[0] = 0; // filter: none
  const png = Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.concat(Array.from({ length: height }, () => row)))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
  pngCache.set(key, png);
  return png;
}

function fulfillImage(route: Route, pathname: string, missingFrames: readonly string[]): Promise<void> {
  const frame = FRAME_PATH_RE.exec(pathname);
  if (frame && missingFrames.includes(pathname)) {
    return route.fulfill({ status: 404, contentType: 'image/png', body: solidPng(...SIZES.missing) });
  }
  // Frames get distinct shades so a screenshot shows the cycle moving.
  const [width, height] = frame ? SIZES[frame[1] as 'sd' | 'mq'] : SIZES.cover;
  const shade = frame ? 60 + Number(frame[2]) * 50 : 128;
  return route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(width, height, shade) });
}

export interface NetworkLog {
  /** Every request the page made, in order, by full URL. */
  requests: string[];
  /** External requests that were blocked; the test fails if any. */
  blocked: string[];
}

interface WatchFixtures {
  missingFrames: readonly string[];
  network: NetworkLog;
}

export const test = base.extend<WatchFixtures>({
  missingFrames: [DEFAULT_MISSING_FRAMES, { option: true }],
  network: [
    async ({ context, baseURL, missingFrames }, use) => {
      const local = new URL(baseURL ?? 'http://127.0.0.1').origin;
      const log: NetworkLog = { requests: [], blocked: [] };
      // One handler for everything: separate routes would need care over
      // which registration wins.
      await context.route('**/*', (route) => {
        const url = new URL(route.request().url());
        log.requests.push(url.href);
        if (url.origin === local) return route.continue();
        if (url.origin === YTIMG) return fulfillImage(route, url.pathname, missingFrames);
        if (url.origin === NOCOOKIE) {
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

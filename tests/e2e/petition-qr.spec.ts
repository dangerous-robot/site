// The QR code carries the DR logo over its centre; this is the gate that the
// result still decodes (A12). Imports test from @playwright/test, not
// ./helpers: the helpers' network fixture fails on any external request and
// the petition page asks for Turnstile and the petition API.
import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { prepareZXingModule, readBarcodes } from 'zxing-wasm/reader';
import { petitionUrl } from '../../src/lib/flyer';

const SLUG = 'prohibit-ai-self-improvement';
const EXPECTED = petitionUrl(SLUG);

// zxing-wasm fetches its binary from jsDelivr unless told otherwise; the
// suite stays offline by handing it the installed file (cwd is the repo root).
const wasm = readFileSync('node_modules/zxing-wasm/dist/reader/zxing_reader.wasm');
prepareZXingModule({ overrides: { wasmBinary: wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength) } });

async function decode(png: Buffer): Promise<string | undefined> {
  const [hit] = await readBarcodes(new Uint8Array(png), { formats: ['QRCode'], tryHarder: true });
  return hit?.text;
}

// A12 asks for the decode in the dark theme: the tile must stay black on
// white there too. With no stored choice Base.astro follows the browser's
// prefers-color-scheme, and Desktop Chrome reports light unless told.
test.use({ colorScheme: 'dark' });

async function expectDarkTheme(page: Page) {
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
}

test.beforeEach(async ({ context, baseURL }) => {
  const local = new URL(baseURL ?? 'http://127.0.0.1').origin;
  await context.route((url) => url.origin !== local, (route) => route.abort('blockedbyclient'));
});

for (const width of [1280, 768]) {
  test(`the page QR decodes to the page URL at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/petitions/${SLUG}`);
    test.skip((await page.locator('[data-status="closed"]').count()) > 0, 'a closed petition shows no QR (A4)');
    await page.waitForLoadState('networkidle'); // the logo <image> must be painted
    await expectDarkTheme(page);
    const tile = page.locator('.petition-qr__tile');
    await expect(tile).toBeVisible();
    expect(await decode(await tile.screenshot())).toBe(EXPECTED);
  });
}

test('the flyer QR decodes to the page URL', async ({ page }) => {
  await page.goto(`/petitions/${SLUG}/flyer`);
  await page.waitForLoadState('networkidle');
  await expectDarkTheme(page);
  expect(await decode(await page.locator('.petition-qr__tile').screenshot())).toBe(EXPECTED);
});

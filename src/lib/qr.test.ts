import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { qrSvg, QR_LOGO_FRACTION, QR_LOGO_HREF } from './qr';

const URL = 'https://dangerousrobot.org/petitions/prohibit-ai-self-improvement';

describe('qrSvg', () => {
  test('is one svg with a title naming the url and no trailing newline', async () => {
    const svg = await qrSvg(URL);
    assert.match(svg, /^<svg[^>]*role="img"/);
    assert.match(svg, new RegExp(`<title>QR code for ${URL}</title>`));
    assert.ok(svg.endsWith('</svg>'), 'trimmed, so the figure stays on one line of built HTML');
  });
  test('escapes the title text', async () => {
    const svg = await qrSvg('https://dangerousrobot.org/p?a=1&b=2');
    assert.match(svg, /<title>QR code for https:\/\/dangerousrobot\.org\/p\?a=1&amp;b=2<\/title>/);
  });
  test('centres the logo on a white square at QR_LOGO_FRACTION', async () => {
    const svg = await qrSvg(URL);
    const [, size] = svg.match(/viewBox="0 0 (\d+) \1"/)!;
    const n = Number(size);
    const img = svg.match(/<image href="([^"]+)" width="([\d.]+)" height="([\d.]+)" x="([\d.]+)" y="([\d.]+)"/)!;
    assert.equal(img[1], QR_LOGO_HREF);
    const w = Number(img[2]);
    assert.equal(w, Number(img[3]));
    assert.ok(Math.abs(w / n - QR_LOGO_FRACTION) < 0.01);
    assert.ok(Math.abs(Number(img[4]) + w / 2 - n / 2) < 0.01, 'x centred');
    assert.ok(Math.abs(Number(img[5]) + w / 2 - n / 2) < 0.01, 'y centred');
    assert.match(svg, /<rect [^>]*fill="#fff"/);
    const modules = n - 8; // viewBox minus the 4-module quiet zone on each side
    assert.ok((w * 1.12) ** 2 / modules ** 2 < 0.3, 'sanity bound only: the e2e decode test is the real gate (A12)');
  });
  test('refuses a non-https url', async () => {
    await assert.rejects(qrSvg('javascript:alert(1)'));
  });
});

import QRCode from 'qrcode';

export const QR_LOGO_HREF = '/dr-logo.png';
// Share of the viewBox width the logo covers. Larger logos stopped decoding
// because the robot's eye resembles a finder pattern; the e2e decode test
// gates any increase.
export const QR_LOGO_FRACTION = 0.14;
const LOGO_PAD = 1.12;

function escapeXml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const num = (v: number) => String(Number(v.toFixed(3)));

/** Inline SVG QR code for `url`, error correction H, with the DR logo on a white square in the centre. */
export async function qrSvg(url: string): Promise<string> {
  if (new URL(url).protocol !== 'https:') throw new Error(`qrSvg: not an https URL: ${url}`);
  // Trimmed so the figure stays on one line of built HTML.
  const raw = (await QRCode.toString(url, { type: 'svg', errorCorrectionLevel: 'H' })).trim();
  const size = raw.match(/viewBox="0 0 (\d+) \1"/);
  if (!raw.startsWith('<svg ') || !raw.endsWith('</svg>') || !size) {
    throw new Error('qrSvg: unexpected output from qrcode');
  }
  const n = Number(size[1]);
  const img = n * QR_LOGO_FRACTION;
  const pad = img * LOGO_PAD;
  const overlay =
    `<rect width="${num(pad)}" height="${num(pad)}" x="${num((n - pad) / 2)}" y="${num((n - pad) / 2)}" fill="#fff"/>` +
    `<image href="${QR_LOGO_HREF}" width="${num(img)}" height="${num(img)}" x="${num((n - img) / 2)}" y="${num((n - img) / 2)}"/>`;
  const openEnd = raw.indexOf('>') + 1;
  const open = raw.slice(0, openEnd).replace(/^<svg /, '<svg role="img" ');
  const body = raw.slice(openEnd, -'</svg>'.length);
  return `${open}<title>QR code for ${escapeXml(url)}</title>${body}${overlay}</svg>`;
}

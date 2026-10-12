// Video durations from the YouTube Data API (contentDetails.duration), which
// uses ISO 8601 durations such as PT22M58S. Live and upcoming videos report
// P0D; days appear on very long streams.

const ISO_DURATION_RE = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/;

/** Seconds, or null when the text is not a day-to-second ISO 8601 duration. */
export function parseIsoDuration(s: string): number | null {
  const match = ISO_DURATION_RE.exec(s);
  if (!match) return null;
  // The regex alone accepts "P" and an empty time part ("PT", "P1DT"),
  // which name no amount of time; both leave nothing after the P or T.
  if (s === 'P' || s.endsWith('T')) return null;
  const [, d, h, m, sec] = match;
  return Number(d ?? 0) * 86400 + Number(h ?? 0) * 3600 + Number(m ?? 0) * 60 + Number(sec ?? 0);
}

const pad2 = (n: number) => String(n).padStart(2, '0');

function hms(sec: number): { h: number; m: number; s: number } {
  const total = Math.max(0, Math.floor(sec));
  return { h: Math.floor(total / 3600), m: Math.floor((total % 3600) / 60), s: total % 60 };
}

/** `m:ss` under an hour, else `h:mm:ss`, matching YouTube's own badge. */
export function formatDuration(sec: number): string {
  const { h, m, s } = hms(sec);
  return h > 0 ? `${h}:${pad2(m)}:${pad2(s)}` : `${m}:${pad2(s)}`;
}

const unit = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** Screen reader text: "22 minutes 58 seconds"; zero parts are left out. */
export function spokenDuration(sec: number): string {
  const { h, m, s } = hms(sec);
  const parts: string[] = [];
  if (h > 0) parts.push(unit(h, 'hour'));
  if (m > 0) parts.push(unit(m, 'minute'));
  if (s > 0 || parts.length === 0) parts.push(unit(s, 'second'));
  return parts.join(' ');
}

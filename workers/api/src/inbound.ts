// Reading a message sent to sign@dangerousrobot.org: the raw header block, Cloudflare's
// own sender check result, the From address and the subject line. Pure functions, so
// every forged or malformed case is tested without a Worker. Anything unclear fails
// closed (null), never open.

export const SIGN_ADDRESS = 'sign@dangerousrobot.org';
export const EMAIL_MAX = 254;
// Email Routing's server id in the result headers it adds.
export const CLOUDFLARE_AUTHSERV_ID = 'mx.cloudflare.net';
// Real header blocks run to tens of KiB; a message is up to 25 MiB, so stop well short.
export const HEADER_MAX_BYTES = 128 * 1024;

export interface RawHeader {
  name: string;
  value: string;
}

/**
 * Plain addresses only. A looser check let `"x"<victim@...>` and `<victim@...>` through as
 * distinct emails that a mail API could deliver to the same inbox, and let shell
 * metacharacters reach the runbook's removal command. Expects a lowercased address.
 */
export function isPlainAddress(email: string): boolean {
  return email.length <= EMAIL_MAX && /^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(email);
}

/**
 * The header block from the top of the raw message, up to the first blank line. Read from
 * `raw` rather than the `headers` object, which merges duplicates and hides their order.
 * null when the block outgrows `maxBytes`.
 */
export async function readHeaderBlock(raw: ReadableStream<Uint8Array>, maxBytes = HEADER_MAX_BYTES): Promise<string | null> {
  const reader = raw.getReader();
  let buf = new Uint8Array(0);
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return buf.length <= maxBytes ? decode(buf) : null;
      const from = Math.max(0, buf.length - 3);
      const next = new Uint8Array(buf.length + value.length);
      next.set(buf);
      next.set(value, buf.length);
      buf = next;
      const end = blankLineAt(buf, from);
      if (end >= 0) return end <= maxBytes ? decode(buf.subarray(0, end)) : null;
      if (buf.length > maxBytes) return null;
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

function blankLineAt(b: Uint8Array, from: number): number {
  for (let i = from; i < b.length - 1; i++) {
    if (b[i] === 10 && (b[i + 1] === 10 || (b[i + 1] === 13 && b[i + 2] === 10))) return i;
    if (b[i] === 13 && b[i + 1] === 10 && b[i + 2] === 13 && b[i + 3] === 10) return i;
  }
  return -1;
}

function decode(b: Uint8Array): string {
  return new TextDecoder('utf-8').decode(b);
}

/** Headers in order, duplicates kept, continuation lines unfolded. */
export function parseHeaders(block: string): RawHeader[] {
  const out: RawHeader[] = [];
  let current: RawHeader | null = null;
  for (const line of block.split(/\r?\n/)) {
    if (line === '') break;
    if (/^[ \t]/.test(line)) {
      if (current) current.value += line;
      continue;
    }
    const colon = line.indexOf(':');
    // A line that is neither a header nor a continuation: skip it and anything folded under it.
    if (colon <= 0) {
      current = null;
      continue;
    }
    current = { name: line.slice(0, colon).trim(), value: line.slice(colon + 1) };
    out.push(current);
  }
  for (const h of out) h.value = h.value.trim();
  return out;
}

/**
 * Splits on `sep` outside quoted strings and comments, dropping comments. null when a quote
 * or comment is left open, or a `)` has no `(`, so a value built to confuse the split fails.
 */
function splitOutside(value: string, sep: string): string[] | null {
  const parts: string[] = [];
  let cur = '';
  let depth = 0;
  let quoted = false;
  for (let i = 0; i < value.length; i++) {
    const c = value[i];
    if (c === '\\' && (quoted || depth > 0)) {
      if (depth === 0) cur += c + (value[i + 1] ?? '');
      i++;
    } else if (depth > 0) {
      if (c === '(') depth++;
      else if (c === ')') depth--;
      if (depth === 0) cur += ' ';
    } else if (quoted) {
      cur += c;
      if (c === '"') quoted = false;
    } else if (c === '"') {
      cur += c;
      quoted = true;
    } else if (c === '(') {
      depth = 1;
    } else if (c === ')') {
      return null;
    } else if (c === sep) {
      parts.push(cur);
      cur = '';
    } else {
      cur += c;
    }
  }
  if (quoted || depth > 0) return null;
  parts.push(cur);
  return parts.map((p) => p.trim());
}

export interface DmarcResult {
  /** `pass`, another DMARC result, or `missing` / `ambiguous` when there is not exactly one. */
  result: string;
  headerFrom: string | null;
}

/**
 * Cloudflare's DMARC verdict, from the topmost authentication result header (plain or ARC).
 * Receiving servers add their headers above what the sender wrote, so only the topmost can
 * be Cloudflare's own; one lower down may have been pasted in by the sender. null when the
 * topmost is missing, from another server, or unreadable.
 */
export function cloudflareDmarc(headers: RawHeader[]): DmarcResult | null {
  const top = headers.find((h) => /^(arc-)?authentication-results$/i.test(h.name));
  if (!top) return null;
  // Fields Cloudflare copies from the sender (envelope address, DKIM selector) can open or
  // close a comment or quote, hiding Cloudflare's own result and exposing an injected one
  // to the parser below. Counted on the raw text, any injected result is a second one.
  const count = (re: RegExp) => top.value.match(re)?.length ?? 0;
  if (count(/(?<![\w.-])dmarc(?![\w-])/gi) > 1 || count(/(?<![\w.-])header\.from(?![\w-])/gi) > 1) {
    return { result: 'ambiguous', headerFrom: null };
  }
  const parts = splitOutside(top.value, ';');
  if (!parts) return null;
  let i = 0;
  if (/^arc-/i.test(top.name)) {
    if (!/^i\s*=\s*\d+$/i.test(parts[0])) return null;
    i = 1;
  }
  if ((parts[i] ?? '').split(/\s+/)[0].toLowerCase() !== CLOUDFLARE_AUTHSERV_ID) return null;

  const dmarc = parts
    .slice(i + 1)
    .map((p) => p.replace(/\s*=\s*/g, '='))
    .filter((p) => /^dmarc=/i.test(p));
  if (dmarc.length !== 1) return { result: dmarc.length === 0 ? 'missing' : 'ambiguous', headerFrom: null };
  const [method, ...props] = dmarc[0].split(/\s+/);
  const from = props.filter((p) => /^header\.from=/i.test(p));
  return {
    result: method.slice('dmarc='.length).toLowerCase(),
    headerFrom: from.length === 1 ? from[0].slice('header.from='.length).replace(/^"|"$/g, '').toLowerCase() : null,
  };
}

// Public suffixes under which people register names (example.co.uk). A suffix missing
// here makes its domains share one cap key: stricter, never looser.
const TWO_LABEL_SUFFIXES = new Set([
  'co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'me.uk', 'ltd.uk', 'plc.uk', 'net.uk',
  'com.au', 'net.au', 'org.au', 'edu.au', 'co.nz', 'org.nz', 'co.jp', 'ne.jp', 'or.jp',
  'co.za', 'com.br', 'com.mx', 'co.in', 'co.kr', 'com.cn', 'com.tw', 'com.sg', 'com.hk',
]);

/**
 * The registered domain, for the per-domain cap: DMARC passes for any subdomain a domain
 * owner signs, so a cap on the full From domain would be one cap per minted subdomain.
 */
export function orgDomain(domain: string): string {
  const labels = domain.split('.');
  const keep = labels.length > 2 && TWO_LABEL_SUFFIXES.has(labels.slice(-2).join('.')) ? 3 : 2;
  return labels.slice(-keep).join('.');
}

export interface FromAddress {
  /** Lowercased plain address. */
  address: string;
  /** Decoded display name, whitespace collapsed; empty when there is none. */
  displayName: string;
}

/** The single From mailbox. null for none, two From headers, a list, a group, or an odd address. */
export function parseFrom(headers: RawHeader[]): FromAddress | null {
  const froms = headers.filter((h) => h.name.toLowerCase() === 'from');
  if (froms.length !== 1) return null;
  const mailboxes = splitOutside(froms[0].value, ',');
  if (!mailboxes || mailboxes.length !== 1) return null;
  const v = mailboxes[0];
  if (splitOutside(v, ':')!.length !== 1 || splitOutside(v, ';')!.length !== 1) return null;
  const angle = /^([^<>]*)<([^<>]*)>$/.exec(v);
  if (!angle && /[<>]/.test(v)) return null;
  const address = (angle ? angle[2] : v).trim().toLowerCase();
  if (!isPlainAddress(address)) return null;
  const display = angle ? angle[1].trim().replace(/"((?:[^"\\]|\\.)*)"/g, (_, q: string) => q.replace(/\\(.)/g, '$1')) : '';
  return { address, displayName: decodeEncodedWords(display).replace(/\s+/g, ' ').trim() };
}

const ENCODED_WORD = /=\?([^?\s]+)\?([bBqQ])\?([^?\s]*)\?=/g;

/**
 * Decodes RFC 2047 encoded words (`=?UTF-8?B?...?=`, `=?UTF-8?Q?...?=`). Whitespace between
 * adjacent encoded words is dropped, and their bytes are joined before decoding, since a
 * mail client may split one character across two words. A word that does not decode is
 * left as written.
 */
export function decodeEncodedWords(s: string): string {
  let out = '';
  let last = 0;
  let run: { charset: string; bytes: number[] } | null = null;
  const flush = () => {
    if (run) out += new TextDecoder(run.charset).decode(new Uint8Array(run.bytes));
    run = null;
  };
  for (const m of s.matchAll(ENCODED_WORD)) {
    const between = s.slice(last, m.index);
    last = m.index + m[0].length;
    const charset = m[1].split('*')[0].toLowerCase();
    const bytes = wordBytes(m[2], m[3]);
    if (!bytes || !knownCharset(charset)) {
      flush();
      out += between + m[0];
      continue;
    }
    const adjacent = run !== null && /^\s*$/.test(between);
    if (adjacent && run!.charset === charset) {
      run!.bytes.push(...bytes);
      continue;
    }
    flush();
    if (!adjacent) out += between;
    run = { charset, bytes };
  }
  flush();
  return out + s.slice(last);
}

function knownCharset(charset: string): boolean {
  try {
    new TextDecoder(charset);
    return true;
  } catch {
    return false;
  }
}

function wordBytes(encoding: string, text: string): number[] | null {
  if (encoding.toLowerCase() === 'b') {
    try {
      return [...atob(text)].map((c) => c.charCodeAt(0));
    } catch {
      return null;
    }
  }
  const bytes: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '_') bytes.push(0x20);
    else if (c === '=') {
      const hex = text.slice(i + 1, i + 3);
      if (!/^[0-9a-fA-F]{2}$/.test(hex)) return null;
      bytes.push(parseInt(hex, 16));
      i += 2;
    } else bytes.push(c.charCodeAt(0));
  }
  return bytes;
}

/** RFC 3834 automatic replies and list or bulk mail: never answered. */
export function isAutoSubmitted(headers: RawHeader[]): boolean {
  const word = (v: string) => (splitOutside(v, ';')?.[0] ?? v).trim().toLowerCase();
  return headers.some((h) => {
    const name = h.name.toLowerCase();
    if (name === 'auto-submitted') return word(h.value) !== 'no';
    if (name === 'precedence') return ['bulk', 'list', 'junk'].includes(word(h.value));
    return false;
  });
}

export interface SignSubject {
  slug: string;
  /** As written, trimmed; empty when the subject has none. */
  name: string;
  showName: boolean;
  wantsUpdates: boolean;
}

/** The subject the last-step page prefills. parseSubject reads it back. */
export function buildSubject({ slug, name, showName, wantsUpdates }: SignSubject): string {
  const yn = (b: boolean) => (b ? 'yes' : 'no');
  return `Sign ${slug} | Name: ${name} | Show my name: ${yn(showName)} | Updates: ${yn(wantsUpdates)}`;
}

const SUBJECT_KEYS: Record<string, keyof Omit<SignSubject, 'slug'>> = { name: 'name', 'show my name': 'showName', updates: 'wantsUpdates' };

/**
 * Reads `Sign <slug> | Name: <name> | Show my name: yes|no | Updates: yes|no` (decoded). Splits
 * only where `|` is followed by a known key, so a `|` inside a name stays in the name. A
 * repeated key or text before the first key makes it unreadable. Consent is yes only when
 * the subject says yes.
 */
export function parseSubject(subject: string): SignSubject | null {
  const m = /^\s*sign\s+([a-z0-9-]+)(.*)$/is.exec(subject);
  if (!m) return null;
  const parts = m[2].split(/\|\s*(name|show my name|updates)\s*:/i);
  if (parts[0].trim() !== '') return null;
  const seen = new Set<string>();
  const out: SignSubject = { slug: m[1].toLowerCase(), name: '', showName: false, wantsUpdates: false };
  for (let i = 1; i < parts.length; i += 2) {
    const key = SUBJECT_KEYS[parts[i].toLowerCase()];
    if (seen.has(key)) return null;
    seen.add(key);
    const value = parts[i + 1].trim();
    if (key === 'name') out.name = value;
    else out[key] = value.toLowerCase() === 'yes';
  }
  return out;
}

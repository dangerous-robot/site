import { describe, expect, it } from 'vitest';
import {
  buildSubject,
  cloudflareDmarc,
  decodeEncodedWords,
  isAutoSubmitted,
  orgDomain,
  parseFrom,
  parseHeaders,
  parseSubject,
  readHeaderBlock,
} from '../src/inbound';

function stream(text: string, chunk = 7): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  let i = 0;
  return new ReadableStream({
    pull(c) {
      if (i >= bytes.length) return c.close();
      c.enqueue(bytes.slice(i, i + chunk));
      i += chunk;
    },
  });
}

const CF = 'ARC-Authentication-Results: i=1; mx.cloudflare.net; dkim=pass header.d=example.com; dmarc=pass header.from=example.com policy.dmarc=none; spf=pass smtp.mailfrom=bounce@example.com';

describe('readHeaderBlock', () => {
  it('stops at the blank line, across chunk boundaries, for CRLF and LF', async () => {
    expect(await readHeaderBlock(stream('A: 1\r\nB: 2\r\n\r\nbody\r\nC: 3'))).toBe('A: 1\r\nB: 2');
    expect(await readHeaderBlock(stream('A: 1\nB: 2\n\nbody'))).toBe('A: 1\nB: 2');
  });

  it('fails closed when the header block outgrows the cap', async () => {
    expect(await readHeaderBlock(stream(`A: ${'x'.repeat(200)}\r\n\r\n`), 100)).toBeNull();
  });

  it('ends at a mixed blank line too', async () => {
    expect(await readHeaderBlock(stream('A: 1\n\r\nFrom: body@example.com'))).toBe('A: 1');
  });

  it('accepts a message with no body', async () => {
    expect(await readHeaderBlock(stream('A: 1\r\nB: 2\r\n'))).toBe('A: 1\r\nB: 2\r\n');
  });
});

describe('parseHeaders', () => {
  it('keeps order and duplicates, and unfolds continuation lines', () => {
    expect(parseHeaders('Received: one\r\nX-A: first\r\n second\r\n\tthird\r\nreceived: two')).toEqual([
      { name: 'Received', value: 'one' },
      { name: 'X-A', value: 'first second\tthird' },
      { name: 'received', value: 'two' },
    ]);
  });

  it('stops at the first empty line', () => {
    expect(parseHeaders('A: 1\r\n\r\nFrom: body@example.com')).toEqual([{ name: 'A', value: '1' }]);
  });
});

describe('cloudflareDmarc', () => {
  const h = (...lines: string[]) => parseHeaders(lines.join('\r\n'));

  it('reads the topmost Cloudflare result, ARC or plain', () => {
    expect(cloudflareDmarc(h(CF))).toEqual({ result: 'pass', headerFrom: 'example.com' });
    expect(cloudflareDmarc(h('Authentication-Results: mx.cloudflare.net; dmarc=fail (p=NONE) header.from=Example.COM'))).toEqual({
      result: 'fail',
      headerFrom: 'example.com',
    });
  });

  it('ignores a pass pasted lower down when the top one fails', () => {
    const top = CF.replace('dmarc=pass', 'dmarc=fail');
    expect(cloudflareDmarc(h(top, 'Subject: x', 'Authentication-Results: mx.cloudflare.net; dmarc=pass header.from=example.com'))).toMatchObject({
      result: 'fail',
    });
  });

  it('fails closed when the topmost result is from another server, even with a Cloudflare pass below', () => {
    expect(cloudflareDmarc(h('Authentication-Results: mail.example.net; dmarc=pass header.from=example.com', CF))).toBeNull();
  });

  it('fails closed with no result header or a garbled one', () => {
    expect(cloudflareDmarc(h('From: a@example.com'))).toBeNull();
    expect(cloudflareDmarc(h('ARC-Authentication-Results: mx.cloudflare.net; dmarc=pass header.from=example.com'))).toBeNull();
    expect(cloudflareDmarc(h('Authentication-Results: mx.cloudflare.net; spf=pass (unclosed comment; dmarc=pass header.from=example.com'))).toBeNull();
  });

  it('does not split inside quoted strings or comments', () => {
    const v = h('Authentication-Results: mx.cloudflare.net; dkim=fail reason="x; y"; spf=none (a; b); dmarc=fail header.from=example.com');
    expect(cloudflareDmarc(v)).toEqual({ result: 'fail', headerFrom: 'example.com' });
  });

  it('refuses a result naming dmarc or header.from twice anywhere, comments and quotes included', () => {
    const v = h('Authentication-Results: mx.cloudflare.net; dkim=fail reason="x; dmarc=pass header.from=evil.example"; dmarc=fail header.from=example.com');
    expect(cloudflareDmarc(v)).toMatchObject({ result: 'ambiguous' });
    // policy.dmarc and smtp.mailfrom are other words.
    expect(cloudflareDmarc(h(CF))).toMatchObject({ result: 'pass' });
  });

  it('refuses a pass injected through fields the sender controls, whatever the comment and quote nesting', () => {
    // An open ( in a sender-chosen field swallows Cloudflare's own result; a later
    // sender-chosen field closes it and adds a pass.
    for (const v of [
      'ARC-Authentication-Results: i=1; mx.cloudflare.net; dkim=fail header.d=attacker.com header.s=s1 header.b=ab(c; dmarc=fail header.from=victim.com; spf=pass smtp.mailfrom="x);dmarc=pass header.from=victim.com \\""@attacker.com',
      'ARC-Authentication-Results: i=1; mx.cloudflare.net; dkim=fail header.d=attacker.com header.s=x((; dmarc=fail header.from=victim.com; spf=pass (domain of x)); dmarc=pass header.from=victim.com @attacker.com) smtp.mailfrom=a@attacker.com',
      'Authentication-Results: mx.cloudflare.net; dkim=fail header.s=a(; dmarc=fail header.from=victim.com; spf=pass smtp.mailfrom=x);dmarc(x)=pass header.from(y)=victim.com@attacker.com',
    ]) {
      expect(cloudflareDmarc(h(v))?.result ?? null, v).not.toBe('pass');
    }
  });

  it('refuses a result with two dmarc entries or none', () => {
    expect(cloudflareDmarc(h('Authentication-Results: mx.cloudflare.net; dmarc=fail header.from=example.com; dmarc=pass header.from=example.com'))).toMatchObject({
      result: 'ambiguous',
    });
    expect(cloudflareDmarc(h('Authentication-Results: mx.cloudflare.net; spf=pass smtp.mailfrom=a@example.com'))).toMatchObject({ result: 'missing' });
  });
});

describe('parseFrom', () => {
  const from = (...values: string[]) => parseFrom(values.map((value) => ({ name: 'From', value })));

  it('reads the address and display name in the common forms', () => {
    expect(from('Jane Doe <Jane.Doe@Example.com>')).toEqual({ address: 'jane.doe@example.com', displayName: 'Jane Doe' });
    expect(from('"Doe, Jane" <jane@example.com>')).toEqual({ address: 'jane@example.com', displayName: 'Doe, Jane' });
    expect(from('jane@example.com')).toEqual({ address: 'jane@example.com', displayName: '' });
    expect(from('jane@example.com (Jane)')).toEqual({ address: 'jane@example.com', displayName: '' });
    expect(from('=?UTF-8?Q?Jos=C3=A9_P=C3=A9rez?= <jose@example.com>')).toEqual({ address: 'jose@example.com', displayName: 'José Pérez' });
  });

  it('refuses two From headers, a list of mailboxes, a group, or an odd address', () => {
    expect(from('a@example.com', 'b@example.com')).toBeNull();
    expect(from('a@example.com, b@example.com')).toBeNull();
    expect(from('a@example.com, Bob <b@example.com>')).toBeNull();
    expect(from('friends: a@example.com;')).toBeNull();
    expect(from('"x"<victim@example.org> <a@example.com>')).toBeNull();
    expect(from("o'b@example.com")).toBeNull();
    expect(parseFrom([])).toBeNull();
  });
});

describe('decodeEncodedWords', () => {
  it('decodes B and Q words, joining adjacent ones without the space between', () => {
    expect(decodeEncodedWords('=?UTF-8?B?Sm9zw6k=?= and =?utf-8?q?caf=C3=A9_au_lait?=')).toBe('José and café au lait');
    // A multi-byte character split across two words.
    expect(decodeEncodedWords('=?UTF-8?Q?Jos=C3?= =?UTF-8?Q?=A9?=')).toBe('José');
    expect(decodeEncodedWords('=?ISO-8859-1?Q?Fran=E7ois?=')).toBe('François');
  });

  it('leaves plain text and malformed words alone', () => {
    expect(decodeEncodedWords('Sign pledge | Name: Ada')).toBe('Sign pledge | Name: Ada');
    expect(decodeEncodedWords('=?UTF-8?B?***?=')).toBe('=?UTF-8?B?***?=');
  });
});

describe('subject', () => {
  it('round-trips what the last-step page builds, including a name with a pipe', () => {
    for (const s of [
      { slug: 'pledge', name: 'Ada Lovelace', showName: false, wantsUpdates: false },
      { slug: 'pledge', name: 'A | B & C <d> "e"', showName: true, wantsUpdates: true },
      { slug: 'pledge', name: 'José Ñúñez', showName: true, wantsUpdates: false },
    ]) {
      expect(parseSubject(buildSubject(s))).toEqual(s);
    }
    expect(buildSubject({ slug: 'pledge', name: 'Jane Doe', showName: false, wantsUpdates: true })).toBe(
      'Sign pledge | Name: Jane Doe | Show my name: no | Updates: yes',
    );
  });

  it('is lenient about case and spacing, and counts only yes as consent', () => {
    expect(parseSubject('sign PLEDGE|name:Jane|show my name: YES|updates: sure')).toEqual({
      slug: 'pledge',
      name: 'Jane',
      showName: true,
      wantsUpdates: false,
    });
    expect(parseSubject('Sign pledge')).toEqual({ slug: 'pledge', name: '', showName: false, wantsUpdates: false });
  });

  it('refuses a subject it cannot read unambiguously', () => {
    expect(parseSubject('Hello')).toBeNull();
    expect(parseSubject('Re: Sign pledge | Name: Jane')).toBeNull();
    expect(parseSubject('Sign pledge junk | Name: Jane')).toBeNull();
    expect(parseSubject('Sign pledge | Name: Ann | Name: Bob')).toBeNull();
  });
});

describe('isAutoSubmitted', () => {
  const auto = (name: string, value: string) => isAutoSubmitted([{ name, value }]);
  it('flags auto-replies and bulk mail, not Auto-Submitted: no', () => {
    expect(auto('Auto-Submitted', 'auto-replied')).toBe(true);
    expect(auto('auto-submitted', 'auto-generated; owner-email="x@example.com"')).toBe(true);
    expect(auto('Precedence', 'bulk')).toBe(true);
    expect(auto('Precedence', 'List')).toBe(true);
    expect(auto('Precedence', 'junk')).toBe(true);
    expect(auto('Auto-Submitted', 'No')).toBe(false);
    expect(auto('Precedence', 'first-class')).toBe(false);
  });
});

describe('orgDomain', () => {
  it('keys subdomains to the registered domain, with common two-label suffixes', () => {
    expect(orgDomain('example.com')).toBe('example.com');
    expect(orgDomain('a1.mail.attacker.com')).toBe('attacker.com');
    expect(orgDomain('mail.example.co.uk')).toBe('example.co.uk');
    expect(orgDomain('example.co.uk')).toBe('example.co.uk');
  });
});

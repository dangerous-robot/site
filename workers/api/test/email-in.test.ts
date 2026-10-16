import { applyD1Migrations, env, reset } from 'cloudflare:test';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import worker, { ADDRESS_DAILY_CAP, DOMAIN_DAILY_CAP, HOURLY_EMAIL_CAP, sendReminders } from '../src/index';

const SITE = 'https://dangerousrobot.org';
const API = 'https://api.dangerousrobot.org';
const SLUG = 'pledge';
const NOT_VERIFIED = 'We could not confirm this message came from your address. Write to contact@dangerousrobot.org.';

interface SentEmail {
  from: string;
  to: string[];
  reply_to: string;
  subject: string;
  text: string;
  headers?: Record<string, string>;
}
let sentEmails: SentEmail[] = [];
let resendStatus = 200;

beforeEach(async () => {
  await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
  await env.DB.prepare(
    "INSERT INTO petitions (slug, title, post_url, status, opened_at) VALUES (?, 'The Pledge', ?, 'open', '2026-10-04T00:00:00.000Z')",
  )
    .bind(SLUG, `${SITE}/writing/pledge`)
    .run();
  sentEmails = [];
  resendStatus = 200;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    expect(String(input instanceof Request ? input.url : input)).toBe('https://api.resend.com/emails');
    const sent = JSON.parse(String(init!.body)) as SentEmail;
    if (resendStatus !== 200) {
      // Resend's error bodies can echo the request, address included.
      return Response.json({ message: `Invalid to: ${sent.to.join(',')}` }, { status: resendStatus });
    }
    sentEmails.push(sent);
    return new Response('{}', { status: 200 });
  });
});

afterEach(async () => {
  vi.restoreAllMocks();
  await reset();
});

/** What Email Routing's own result looks like for a message from `domain`. */
function cfResult(domain: string, dmarc = 'pass'): string {
  return (
    `ARC-Authentication-Results: i=1; mx.cloudflare.net;\r\n dkim=pass header.d=${domain} header.s=s1 header.b=abc;\r\n` +
    ` dmarc=${dmarc} header.from=${domain} policy.dmarc=none;\r\n spf=pass (mx.cloudflare.net: domain of bounce@${domain} designates 192.0.2.1 as permitted sender) smtp.mailfrom=bounce@${domain}`
  );
}

interface MailOpts {
  from?: string;
  subject?: string;
  /** The topmost result header; null leaves it out. Defaults to a pass for the From domain. */
  auth?: string | null;
  /** Headers between the result header and From. */
  extra?: string[];
  /** Headers after Subject, where anything the sender wrote sits. */
  below?: string[];
}

function rawMail(o: MailOpts = {}): string {
  const from = o.from ?? 'Ada Lovelace <ada@example.com>';
  const domain = /@([^>\s]+)/.exec(from)![1].toLowerCase();
  const lines = [
    ...(o.auth === null ? [] : [o.auth ?? cfResult(domain)]),
    'Received: from mail.example.com by mx.cloudflare.net',
    ...(o.extra ?? []),
    `From: ${from}`,
    'To: sign@dangerousrobot.org',
    `Subject: ${o.subject ?? 'Sign pledge | Name: Ada Lovelace | Show my name: yes | Updates: no'}`,
    'Message-ID: <1@example.com>',
    ...(o.below ?? []),
  ];
  return `${lines.join('\r\n')}\r\n\r\nSent from my phone\r\n`;
}

function fakeMessage(raw: string) {
  const bytes = new TextEncoder().encode(raw);
  return {
    from: 'bounce@example.com',
    to: 'sign@dangerousrobot.org',
    raw: new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes);
        c.close();
      },
    }),
    headers: new Headers(),
    rawSize: bytes.length,
    setReject: vi.fn(),
    forward: vi.fn(),
    reply: vi.fn(),
  };
}

async function deliver(o: MailOpts = {}) {
  const msg = fakeMessage(rawMail(o));
  await worker.email(msg as unknown as ForwardableEmailMessage, env);
  // The design does not rely on reply() or forward(); receipts go through Resend.
  expect(msg.reply).not.toHaveBeenCalled();
  expect(msg.forward).not.toHaveBeenCalled();
  return msg;
}

interface Row {
  id: number;
  name: string;
  email: string;
  display_consent: number;
  updates_consent: number;
  confirmed_at: string | null;
  token_hash: string;
  source: string;
}

async function rows(): Promise<Row[]> {
  return (await env.DB.prepare('SELECT * FROM signatures ORDER BY id').all<Row>()).results;
}

async function sha256(s: string): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)));
  return [...d].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** A web signature row as sign() leaves it, with a known token. */
async function webRow(email: string, token: string, confirmed: boolean) {
  await env.DB.prepare(
    `INSERT INTO signatures (petition_slug, name, email, display_consent, updates_consent, created_at, confirmed_at, token_hash)
     VALUES (?, 'Web Name', ?, 0, 0, ?, ?, ?)`,
  )
    .bind(SLUG, email, new Date(Date.now() - 5 * 86_400_000).toISOString(), confirmed ? new Date().toISOString() : null, await sha256(token))
    .run();
}

function removeLink(text: string): string {
  return new RegExp(`/petitions/${SLUG}/remove\\?t=([0-9a-f]+)`).exec(text)![1];
}

function postRemove(token: string): Promise<Response> {
  return worker.fetch(
    new Request(`${API}/petitions/${SLUG}/remove`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ t: token }),
    }),
    env,
  );
}

function seedSends(n: number) {
  return env.DB.batch(
    Array.from({ length: n }, () => env.DB.prepare('INSERT INTO email_sends (sent_at) VALUES (?)').bind(new Date(Date.now() - 60_000).toISOString())),
  );
}

async function expectRejectedSilently(msg: ReturnType<typeof fakeMessage>, reason = NOT_VERIFIED) {
  expect(msg.setReject).toHaveBeenCalledWith(reason);
  expect(await rows()).toHaveLength(0);
  expect(sentEmails).toHaveLength(0);
}

describe('sign by email: a verified message', () => {
  it('stores a confirmed email signature and sends one receipt whose removal link works (T2)', async () => {
    const msg = await deliver();
    expect(msg.setReject).not.toHaveBeenCalled();
    const [row] = await rows();
    expect(row).toMatchObject({ name: 'Ada Lovelace', email: 'ada@example.com', display_consent: 1, updates_consent: 0, source: 'email' });
    expect(row.confirmed_at).not.toBeNull();
    expect(sentEmails).toHaveLength(1);
    const mail = sentEmails[0];
    expect(mail).toMatchObject({ to: ['ada@example.com'], reply_to: 'contact@dangerousrobot.org', headers: { 'Auto-Submitted': 'auto-replied' } });
    expect(mail.text).toContain('Your signature on "The Pledge" is counted.');
    expect(mail.text).toContain('contact@dangerousrobot.org');
    expect((await env.DB.prepare('SELECT COUNT(*) AS n FROM email_sends').first<{ n: number }>())!.n).toBe(1);
    expect((await postRemove(removeLink(mail.text))).status).toBe(200);
    expect(await rows()).toHaveLength(0);
  });

  it('counts the signature on the public tally at once (Q-N2)', async () => {
    await deliver();
    const res = await worker.fetch(new Request(`${API}/petitions/${SLUG}`), env);
    expect(await res.json()).toMatchObject({ count: 1, names: ['Ada Lovelace'] });
  });

  it('accepts a plain Authentication-Results header from Cloudflare too', async () => {
    const msg = await deliver({ auth: 'Authentication-Results: mx.cloudflare.net; dmarc=pass header.from=example.com' });
    expect(msg.setReject).not.toHaveBeenCalled();
    expect(await rows()).toHaveLength(1);
  });
});

describe('sign by email: sender checks', () => {
  it('rejects when the topmost Cloudflare result fails, whatever a lower header says (T3), and the genuine header passes (control)', async () => {
    const forged = 'Authentication-Results: mx.cloudflare.net; dmarc=pass header.from=example.com';
    await expectRejectedSilently(await deliver({ auth: cfResult('example.com', 'fail'), below: [forged] }));
    await expectRejectedSilently(await deliver({ auth: cfResult('example.com', 'fail'), extra: [forged, `ARC-${forged}`] }));
    // Control: the same message with the genuine passing header signs.
    expect((await deliver({ below: [forged] })).setReject).not.toHaveBeenCalled();
    expect(await rows()).toHaveLength(1);
  });

  it('rejects a DMARC pass for a different domain than the From address (T4), control passes', async () => {
    await expectRejectedSilently(await deliver({ auth: cfResult('attacker.example') }));
    expect((await deliver({ auth: cfResult('example.com') })).setReject).not.toHaveBeenCalled();
  });

  it('fails closed with no result header (T5), logging no-auth-header', async () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    await expectRejectedSilently(await deliver({ auth: null }));
    expect(log).toHaveBeenCalledWith('email-sign: no-auth-header');
    // Control: with the genuine header it signs.
    expect((await deliver()).setReject).not.toHaveBeenCalled();
  });

  it('fails closed when a pasted Cloudflare pass sits under another server\'s result', async () => {
    await expectRejectedSilently(
      await deliver({ auth: 'Authentication-Results: relay.example.net; dmarc=pass header.from=example.com', extra: [cfResult('example.com')] }),
    );
  });

  it('rejects two From headers or a From with two addresses', async () => {
    await expectRejectedSilently(await deliver({ extra: ['From: Victim <victim@example.com>'] }));
    await expectRejectedSilently(await deliver({ from: 'ada@example.com, victim@example.com' }));
  });

  it('drops auto-replies and bulk mail without a reply (T6)', async () => {
    for (const header of ['Auto-Submitted: auto-replied', 'Precedence: bulk']) {
      const msg = await deliver({ below: [header] });
      expect(msg.setReject).not.toHaveBeenCalled();
    }
    expect(await rows()).toHaveLength(0);
    expect(sentEmails).toHaveLength(0);
    // Control: Auto-Submitted: no is a person.
    await deliver({ below: ['Auto-Submitted: no'] });
    expect(await rows()).toHaveLength(1);
  });
});

describe('sign by email: existing signatures', () => {
  it('confirms an unconfirmed web signature with the emailed name and choices, so no reminder goes out (T7)', async () => {
    await webRow('ada@example.com', 'web-token', false);
    await deliver({ from: 'ada@Example.com', subject: 'Sign pledge | Name: Ada L | Show my name: yes | Updates: yes' });
    const all = await rows();
    expect(all).toHaveLength(1);
    expect(all[0]).toMatchObject({ name: 'Ada L', display_consent: 1, updates_consent: 1, source: 'email' });
    expect(all[0].confirmed_at).not.toBeNull();
    expect(sentEmails).toHaveLength(1);
    await sendReminders(env, new Date(Date.now() + 86_400_000));
    expect(sentEmails).toHaveLength(1);
  });

  it('leaves a confirmed signature\'s data alone and replaces its removal link only once the receipt is sent', async () => {
    await webRow('ada@example.com', 'old-token', true);
    await deliver({ subject: 'Sign pledge | Name: Someone Else | Show my name: yes | Updates: yes' });
    const [row] = await rows();
    expect(row).toMatchObject({ name: 'Web Name', display_consent: 0, updates_consent: 0, source: 'web' });
    expect(sentEmails).toHaveLength(1);
    expect((await postRemove('old-token')).status).toBe(400);
    expect((await postRemove(removeLink(sentEmails[0].text))).status).toBe(200);
  });
});

describe('sign by email: caps', () => {
  it(`rejects the ${DOMAIN_DAILY_CAP + 1}th message from one domain in a day; a large provider at the same count still signs (T8)`, async () => {
    for (let i = 0; i < DOMAIN_DAILY_CAP; i++) {
      expect((await deliver({ from: `p${i}@small.example` })).setReject).not.toHaveBeenCalled();
    }
    const over = await deliver({ from: 'late@small.example' });
    expect(over.setReject).toHaveBeenCalledWith(expect.stringContaining('Too many'));
    expect((await rows()).some((r) => r.email === 'late@small.example')).toBe(false);
    // Mixed case is the same domain.
    expect((await deliver({ from: 'Late@Small.Example' })).setReject).toHaveBeenCalled();

    for (let i = 0; i <= DOMAIN_DAILY_CAP; i++) {
      expect((await deliver({ from: `g${i}@gmail.com` })).setReject).not.toHaveBeenCalled();
    }
    expect((await rows()).filter((r) => r.email.endsWith('@gmail.com'))).toHaveLength(DOMAIN_DAILY_CAP + 1);
  });

  it('counts subdomains of one registered domain together', async () => {
    for (let i = 0; i < DOMAIN_DAILY_CAP; i++) {
      expect((await deliver({ from: `p@a${i}.attacker.example` })).setReject).not.toHaveBeenCalled();
    }
    expect((await deliver({ from: 'p@zz.attacker.example' })).setReject).toHaveBeenCalledWith(expect.stringContaining('Too many'));
  });

  it(`answers at most ${ADDRESS_DAILY_CAP} messages a day from one address, large providers included`, async () => {
    for (let i = 0; i < ADDRESS_DAILY_CAP; i++) await deliver({ from: 'busy@gmail.com', subject: 'junk' });
    expect(sentEmails).toHaveLength(ADDRESS_DAILY_CAP);
    const over = await deliver({ from: 'Busy@Gmail.com', subject: 'junk' });
    expect(over.setReject).toHaveBeenCalledWith(expect.stringContaining('Too many'));
    expect(sentEmails).toHaveLength(ADDRESS_DAILY_CAP);
    // Another address at the same provider is unaffected.
    expect((await deliver({ from: 'calm@gmail.com' })).setReject).not.toHaveBeenCalled();
  });

  it('stops replies to one domain at the cap, unknown petitions included (T13)', async () => {
    for (let i = 0; i < DOMAIN_DAILY_CAP; i++) await deliver({ from: `u${i}@small.example`, subject: 'Sign nope | Name: X' });
    expect(sentEmails).toHaveLength(DOMAIN_DAILY_CAP);
    const over = await deliver({ from: 'u-last@small.example', subject: 'Sign nope | Name: X' });
    expect(over.setReject).toHaveBeenCalled();
    expect(sentEmails).toHaveLength(DOMAIN_DAILY_CAP);
  });

  it('stores the signature but sends no receipt once the hourly cap is reached, keeping the old removal link (T9)', async () => {
    await webRow('kept@example.com', 'old-token', true);
    await seedSends(HOURLY_EMAIL_CAP);
    await deliver({ from: 'new@example.com' });
    await deliver({ from: 'kept@example.com' });
    expect(sentEmails).toHaveLength(0);
    const all = await rows();
    expect(all.find((r) => r.email === 'new@example.com')!.confirmed_at).not.toBeNull();
    expect(all.find((r) => r.email === 'kept@example.com')!.token_hash).toBe(await sha256('old-token'));
    expect((await postRemove('old-token')).status).toBe(200);
  });

  it('keeps the old removal link when the receipt fails to send', async () => {
    await webRow('kept@example.com', 'old-token', false);
    resendStatus = 500;
    await deliver({ from: 'kept@example.com' });
    const [row] = await rows();
    expect(row.confirmed_at).not.toBeNull();
    expect(row.token_hash).toBe(await sha256('old-token'));
    expect((await env.DB.prepare('SELECT COUNT(*) AS n FROM email_sends').first<{ n: number }>())!.n).toBe(0);
  });
});

describe('sign by email: subject and name', () => {
  it('decodes an encoded-word subject with a non-ASCII name (T10)', async () => {
    const subject = 'Sign pledge | Name: José Ñúñez | Show my name: yes | Updates: no';
    const b64 = btoa(String.fromCharCode(...new TextEncoder().encode(subject)));
    await deliver({ subject: `=?UTF-8?B?${b64}?=` });
    expect((await rows())[0].name).toBe('José Ñúñez');
  });

  it('falls back to the display name when the subject has none (T10)', async () => {
    await deliver({ from: '"Lovelace, Ada" <ada@example.com>', subject: 'Sign pledge' });
    expect((await rows())[0]).toMatchObject({ name: 'Lovelace, Ada', display_consent: 0, updates_consent: 0 });
  });

  it('keeps a name containing a pipe intact (T10)', async () => {
    await deliver({ subject: 'Sign pledge | Name: Ada | Lovelace | Show my name: no | Updates: no' });
    expect((await rows())[0].name).toBe('Ada | Lovelace');
  });

  it('asks for a name when neither the subject nor the address has one (T10)', async () => {
    await deliver({ from: 'ada@example.com', subject: 'Sign pledge' });
    expect(await rows()).toHaveLength(0);
    expect(sentEmails).toHaveLength(1);
    expect(sentEmails[0].text).toContain('Name:');
    expect(sentEmails[0].headers).toEqual({ 'Auto-Submitted': 'auto-replied' });
  });
});

describe('sign by email: petitions', () => {
  it('stores nothing for a closed or unknown petition and replies saying so (T11)', async () => {
    await deliver({ subject: 'Sign no-such-petition | Name: Ada' });
    await deliver({ subject: 'Hello there' });
    await env.DB.prepare("UPDATE petitions SET status = 'closed', closed_at = '2026-12-01T00:00:00.000Z'").run();
    await deliver();
    expect(await rows()).toHaveLength(0);
    expect(sentEmails).toHaveLength(3);
    expect(sentEmails[0].text).toContain('could not tell which petition');
    expect(sentEmails[1].text).toContain('could not tell which petition');
    expect(sentEmails[2].text).toContain('closed on 2026-12-01');
  });
});

describe('sign by email: errors', () => {
  it('rejects rather than drops a message it cannot process, logging only a code', async () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    await env.DB.prepare('DROP TABLE email_in_counts').run();
    const msg = await deliver({ from: 'ada@small.example' });
    expect(msg.setReject).toHaveBeenCalledWith(expect.stringContaining('contact@dangerousrobot.org'));
    expect(log).toHaveBeenCalledWith('email-sign: error');
    expect(sentEmails).toHaveLength(0);
  });
});

describe('sign by email: logs', () => {
  it('logs outcome codes only, never an address, domain or name (T12)', async () => {
    const logged: unknown[] = [];
    for (const method of ['log', 'info', 'warn', 'error', 'debug'] as const) {
      vi.spyOn(console, method).mockImplementation((...args) => void logged.push(...args));
    }
    await deliver({ from: 'Secret Person <secret.person@private-domain.example>' });
    await deliver({ from: 'Secret Person <secret.person@private-domain.example>', auth: null });
    await deliver({ from: 'Secret Person <secret.person@private-domain.example>', auth: cfResult('private-domain.example', 'fail') });
    await deliver({ from: 'secret.person@private-domain.example', subject: 'Sign pledge' });
    await deliver({ from: 'Secret Person <secret.person@private-domain.example>', subject: 'Sign nope | Name: Secret Person' });
    resendStatus = 422;
    await deliver({ from: 'Secret Person <other.secret@private-domain.example>' });
    const text = logged.map((x) => (x instanceof Error ? `${x.message} ${x.stack}` : String(x))).join('\n');
    expect(logged.length).toBeGreaterThan(0);
    for (const secret of ['secret.person', 'other.secret', 'private-domain', 'Secret Person', '@']) expect(text).not.toContain(secret);
    expect(text).toMatch(/^email-sign: /m);
  });
});

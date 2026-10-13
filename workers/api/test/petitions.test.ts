import { applyD1Migrations, env, reset } from 'cloudflare:test';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import worker, { cleanup, HOURLY_EMAIL_CAP, sendReminders } from '../src/index';

const SITE = 'https://dangerousrobot.org';
const API = 'https://api.dangerousrobot.org';
const SLUG = 'pledge';
let ipCounter = 0;

interface SentEmail {
  from: string;
  to: string[];
  reply_to: string;
  subject: string;
  text: string;
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
  // Stand in for the Resend API so tests see the exact request the Worker sends.
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    expect(String(input instanceof Request ? input.url : input)).toBe('https://api.resend.com/emails');
    sentEmails.push(JSON.parse(String(init!.body)));
    return new Response('{}', { status: resendStatus });
  });
});

afterEach(async () => {
  vi.restoreAllMocks();
  await reset();
});

function call(path: string, init: RequestInit = {}): Promise<Response> {
  return worker.fetch(new Request(`${API}${path}`, init), env);
}

interface SignOpts {
  name?: string;
  email?: string;
  /** true sends a checked box; a string sends that raw show_name value. */
  consent?: boolean | string;
  /** true sends a checked updates box; a string sends that raw updates value. */
  updates?: boolean | string;
  honeypot?: string;
  elapsed?: number;
  json?: boolean;
  ip?: string;
  origin?: string | null;
}

function sign(o: SignOpts = {}): Promise<Response> {
  const body = new URLSearchParams({
    name: o.name ?? 'Ada Lovelace',
    email: o.email ?? `signer${++ipCounter}@example.org`,
    website: o.honeypot ?? '',
    elapsed: String(o.elapsed ?? 10_000),
  });
  if (typeof o.consent === 'string') body.set('show_name', o.consent);
  else if (o.consent) body.set('show_name', 'on');
  if (typeof o.updates === 'string') body.set('updates', o.updates);
  else if (o.updates) body.set('updates', 'on');
  const headers: Record<string, string> = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'CF-Connecting-IP': o.ip ?? `10.0.0.${++ipCounter}`,
  };
  if (o.origin !== null) headers.Origin = o.origin ?? SITE;
  if (o.json !== false) headers.Accept = 'application/json';
  return call(`/petitions/${SLUG}/sign`, { method: 'POST', headers, body });
}

/** Token from the last sent email's link for the given action. */
function lastToken(action: 'confirm' | 'remove'): string {
  const text = sentEmails.at(-1)!.text;
  return new RegExp(`/petitions/${SLUG}/${action}\\?t=([0-9a-f]+)`).exec(text)![1];
}

function post(action: 'confirm' | 'remove', token: string): Promise<Response> {
  return call(`/petitions/${SLUG}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ t: token }),
  });
}

async function signAndConfirm(o: SignOpts = {}): Promise<Response> {
  expect((await sign(o)).status).toBe(200);
  return post('confirm', lastToken('confirm'));
}

async function publicJson() {
  const res = await call(`/petitions/${SLUG}`, { headers: { Origin: SITE } });
  return { res, body: (await res.json()) as { status: string; count: number; names: string[] } };
}

function closePetition() {
  return env.DB.prepare("UPDATE petitions SET status = 'closed', closed_at = '2026-12-01T00:00:00.000Z'").run();
}

async function rowCount(): Promise<number> {
  return (await env.DB.prepare('SELECT COUNT(*) AS n FROM signatures').first<{ n: number }>())!.n;
}

describe('signing and consent', () => {
  it('counts confirmed signers and lists only those who opted in', async () => {
    await signAndConfirm({ name: 'Shown Person', consent: true });
    await signAndConfirm({ name: 'Hidden Person' });
    const { res, body } = await publicJson();
    expect(body.count).toBe(2);
    expect(body.names).toEqual(['Shown Person']);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe(SITE);
    expect(res.headers.get('Cache-Control')).toBe('no-store');
  });

  it('records consent on the row with its timestamp', async () => {
    await signAndConfirm({ email: 'yes@example.org', consent: true });
    await signAndConfirm({ email: 'no@example.org' });
    const rows = await env.DB.prepare('SELECT email, display_consent, created_at FROM signatures ORDER BY email').all();
    expect(rows.results).toMatchObject([
      { email: 'no@example.org', display_consent: 0 },
      { email: 'yes@example.org', display_consent: 1 },
    ]);
    expect(rows.results.every((r) => typeof r.created_at === 'string')).toBe(true);
  });

  it('treats only a checked box as consent to show the name', async () => {
    for (const value of ['', '0', 'false']) await sign({ email: `v${value}@example.org`, consent: value });
    const rows = await env.DB.prepare('SELECT display_consent FROM signatures').all<{ display_consent: number }>();
    expect(rows.results.map((r) => r.display_consent)).toEqual([0, 0, 0]);
  });

  it('never shows an email address in the public JSON', async () => {
    await signAndConfirm({ consent: true });
    const res = await call(`/petitions/${SLUG}`);
    expect(await res.text()).not.toContain('@');
  });

  it('thanks the signer with a stable signatory number', async () => {
    await signAndConfirm();
    await sign();
    const token = lastToken('confirm');
    expect(await (await post('confirm', token)).text()).toContain('You are signatory 2.');
    expect(await (await post('confirm', token)).text()).toContain('You are signatory 2.');
  });

  it('does not count unconfirmed signatures', async () => {
    await sign();
    expect((await publicJson()).body.count).toBe(0);
    const row = await env.DB.prepare('SELECT confirmed_at FROM signatures').first();
    expect(row!.confirmed_at).toBeNull();
  });

  it('reports a Resend failure to the signer', async () => {
    resendStatus = 500;
    const res = await sign();
    expect(res.status).toBe(502);
    expect(((await res.json()) as { error: string }).error).toContain('could not send');
  });

  it('lets the signer retry at once after a Resend failure', async () => {
    resendStatus = 500;
    expect((await sign({ email: 'retry@example.org' })).status).toBe(502);
    resendStatus = 200;
    expect((await sign({ email: 'retry@example.org' })).status).toBe(200);
    expect(sentEmails).toHaveLength(2);
    expect(await rowCount()).toBe(1);
  });

  it('rejects a missing name or a malformed email', async () => {
    expect((await sign({ name: '  ' })).status).toBe(400);
    expect((await sign({ email: 'not-an-email' })).status).toBe(400);
    expect(await rowCount()).toBe(0);
  });

  it('accepts only a plain address, so a wrapped address cannot route mail elsewhere', async () => {
    // A mail API may parse `Name <addr>` or `<addr>` and deliver to the inner
    // address, which lets one inbox be targeted under many distinct "emails".
    // Shell metacharacters are refused so the runbook's removal command stays safe.
    for (const email of ['"x"<victim@example.org>', '<victim@example.org>', 'x$(id)@example.com', "o'b@example.com", 'a@b']) {
      expect((await sign({ email })).status, email).toBe(400);
    }
    expect(await rowCount()).toBe(0);
    expect(sentEmails).toHaveLength(0);
    // Control: a plus tag is an ordinary address and must still work.
    expect((await sign({ email: 'a+b@example.com' })).status).toBe(200);
    expect(sentEmails.at(-1)!.to).toEqual(['a+b@example.com']);
  });

  it('sends a plain text email through Resend with confirm and remove links on the API host', async () => {
    await sign({ email: 'Mixed@Example.org' });
    const mail = sentEmails.at(-1)!;
    expect(mail).toMatchObject({
      from: 'Dangerous Robot <no-reply@dangerousrobot.org>',
      to: ['mixed@example.org'],
      reply_to: 'contact@dangerousrobot.org',
    });
    expect(mail).not.toHaveProperty('html');
    expect(mail.text).toContain(`${API}/petitions/${SLUG}/confirm?t=`);
    expect(mail.text).toContain(`${API}/petitions/${SLUG}/remove?t=`);
  });

  it('shows the signer the name and display choice they are confirming', async () => {
    // A re-sign can change both, so the address owner must see what the link will confirm.
    await sign({ name: 'Grace Hopper', consent: true, updates: true });
    expect(sentEmails.at(-1)!.text).toContain('Name: Grace Hopper\nShown on the public list: yes\nEmail updates about this campaign: yes');
    await sign({ name: 'Alan Turing' });
    expect(sentEmails.at(-1)!.text).toContain('Name: Alan Turing\nShown on the public list: no\nEmail updates about this campaign: no');
    expect(sentEmails.at(-1)!.text).toContain('a newer email replaces');
  });
});

describe('email updates opt-in', () => {
  const updatesConsent = async (email: string) =>
    (await env.DB.prepare('SELECT updates_consent AS u FROM signatures WHERE email = ?').bind(email).first<{ u: number }>())!.u;

  it('records the choice only for a checked box', async () => {
    await sign({ email: 'yes@example.org', updates: true });
    await sign({ email: 'no@example.org' });
    expect(await updatesConsent('yes@example.org')).toBe(1);
    expect(await updatesConsent('no@example.org')).toBe(0);
  });

  it('treats only a checked box as consent to updates', async () => {
    for (const raw of ['1', 'true', 'yes', '']) {
      expect((await sign({ email: `raw-${raw || 'empty'}@example.org`, updates: raw })).status).toBe(200);
      expect(await updatesConsent(`raw-${raw || 'empty'}@example.org`)).toBe(0);
    }
  });

  it('keeps a confirmed signer\'s choice when they sign again', async () => {
    await signAndConfirm({ email: 'kept@example.org', updates: true });
    await sign({ email: 'kept@example.org' });
    expect(await updatesConsent('kept@example.org')).toBe(1);
  });

  it('takes the newer choice when an unconfirmed signer signs again', async () => {
    await sign({ email: 'again@example.org', updates: true });
    await env.DB.prepare("UPDATE signatures SET created_at = '2026-01-01T00:00:00.000Z'").run();
    await sign({ email: 'again@example.org' });
    expect(await updatesConsent('again@example.org')).toBe(0);
  });
});

describe('repeat signatures', () => {
  it('re-sends with a fresh token while unconfirmed, keeping one row', async () => {
    await sign({ email: 'again@example.org' });
    const first = lastToken('confirm');
    await env.DB.prepare("UPDATE signatures SET created_at = '2000-01-01T00:00:00.000Z'").run();
    await sign({ email: 'again@example.org' });
    expect(sentEmails).toHaveLength(2);
    expect(await rowCount()).toBe(1);
    expect((await post('confirm', first)).status).toBe(400);
    expect((await post('confirm', lastToken('confirm'))).status).toBe(200);
  });

  it('sends at most one email per address within ten minutes', async () => {
    const first = await sign({ email: 'flood@example.org' });
    const second = await sign({ email: 'flood@example.org' });
    expect(await second.json()).toEqual(await first.json());
    expect(sentEmails).toHaveLength(1);
  });

  it('gives a confirmed address the same reply and sends nothing', async () => {
    await signAndConfirm({ email: 'done@example.org' });
    const res = await sign({ email: 'done@example.org', name: 'Someone Else' });
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true });
    expect(sentEmails).toHaveLength(1);
    const row = await env.DB.prepare('SELECT name FROM signatures').first();
    expect(row!.name).toBe('Ada Lovelace');
  });
});

describe('removal', () => {
  it('removes the row through the email link and drops the count', async () => {
    await signAndConfirm({ consent: true, name: 'Leaving Person' });
    expect((await publicJson()).body.count).toBe(1);
    const res = await post('remove', lastToken('remove'));
    expect(res.status).toBe(200);
    expect(await rowCount()).toBe(0);
    const { body } = await publicJson();
    expect(body.count).toBe(0);
    expect(body.names).toEqual([]);
  });

  it('reports an already-used removal link without error', async () => {
    await signAndConfirm();
    const token = lastToken('remove');
    await post('remove', token);
    expect((await post('remove', token)).status).toBe(400);
  });
});

describe('email link scanners', () => {
  it('changes nothing on GET of the confirm or remove link', async () => {
    await sign();
    const token = lastToken('confirm');
    for (const action of ['confirm', 'remove']) {
      const res = await call(`/petitions/${SLUG}/${action}?t=${encodeURIComponent(token)}`);
      expect(res.status).toBe(200);
      expect(await res.text()).toContain('<form method="post"');
    }
    const row = await env.DB.prepare('SELECT confirmed_at FROM signatures').first();
    expect(row!.confirmed_at).toBeNull();
  });

  it('rejects a malformed token', async () => {
    expect((await post('confirm', 'garbage')).status).toBe(400);
    expect((await post('confirm', '')).status).toBe(400);
  });

  it('answers a body that is not a form with 400, not a crash', async () => {
    const bad = { method: 'POST', headers: { Origin: SITE, 'Content-Type': 'application/json' }, body: '{}' };
    expect((await call(`/petitions/${SLUG}/sign`, bad)).status).toBe(400);
    expect((await call(`/petitions/${SLUG}/confirm`, bad)).status).toBe(400);
    expect((await call(`/petitions/${SLUG}/sign`, { method: 'POST', headers: { Origin: SITE } })).status).toBe(400);
  });

  it('serves pages that leak no token through Referer', async () => {
    const res = await call(`/petitions/${SLUG}/confirm?t=abc`);
    expect(res.headers.get('Referrer-Policy')).toBe('no-referrer');
  });
});

describe('spam layers', () => {
  it('answers a filled honeypot like a success and stores nothing', async () => {
    const res = await sign({ honeypot: 'http://spam.example' });
    expect(res.status).toBe(200);
    expect(await rowCount()).toBe(0);
    expect(sentEmails).toHaveLength(0);
  });

  it('answers a too-fast submission like a success and stores nothing', async () => {
    const res = await sign({ elapsed: 500 });
    expect(res.status).toBe(200);
    expect(await rowCount()).toBe(0);
  });

  it('accepts a submission with no timestamp (the no-JS form)', async () => {
    const body = new URLSearchParams({ name: 'No Script', email: 'nojs@example.org' });
    const res = await call(`/petitions/${SLUG}/sign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'CF-Connecting-IP': '10.9.9.9' },
      body,
    });
    expect(res.status).toBe(200);
    expect(await rowCount()).toBe(1);
  });

  it('returns 429 on the sixth attempt in a minute from one IP', async () => {
    const statuses = [];
    for (let i = 0; i < 6; i++) statuses.push((await sign({ ip: '192.0.2.1' })).status);
    expect(statuses).toEqual([200, 200, 200, 200, 200, 429]);
  });

  it('stops sending confirmation emails once the hourly cap is reached', async () => {
    const seed = (n: number, ageMs: number) =>
      env.DB.batch(
        Array.from({ length: n }, () =>
          env.DB.prepare('INSERT INTO email_sends (sent_at) VALUES (?)').bind(new Date(Date.now() - ageMs).toISOString()),
        ),
      );
    await seed(HOURLY_EMAIL_CAP, 61 * 60_000);
    await seed(HOURLY_EMAIL_CAP - 1, 60_000);
    expect((await sign()).status).toBe(200);
    expect(sentEmails).toHaveLength(1);
    const res = await sign();
    expect(res.status).toBe(429);
    expect(sentEmails).toHaveLength(1);
    expect(await rowCount()).toBe(1);
  });

  it('counts re-sends to one address toward the hourly cap', async () => {
    for (let i = 0; i <= HOURLY_EMAIL_CAP; i++) {
      // Age the row past the resend window so each POST is due a fresh email.
      await env.DB.prepare("UPDATE signatures SET created_at = '2000-01-01T00:00:00.000Z'").run();
      const res = await sign({ email: 'target@example.org' });
      expect(res.status).toBe(i < HOURLY_EMAIL_CAP ? 200 : 429);
    }
    expect(sentEmails).toHaveLength(HOURLY_EMAIL_CAP);
  });

  it('refuses a browser POST from another origin', async () => {
    expect((await sign({ origin: 'https://evil.example' })).status).toBe(403);
    // Sandboxed iframes send "null"; accepting it would void this check.
    expect((await sign({ origin: 'null' })).status).toBe(403);
    expect(await rowCount()).toBe(0);
  });
});

describe('closed petitions', () => {
  it('refuses new signatures and reports closed status', async () => {
    await closePetition();
    const res = await sign();
    expect(res.status).toBe(409);
    expect(((await res.json()) as { error: string }).error).toContain('closed on 2026-12-01');
    expect((await publicJson()).body.status).toBe('closed');
  });
});

describe('no-JS path', () => {
  it('returns a check-your-email page that links back to the post', async () => {
    const res = await sign({ json: false });
    expect(res.headers.get('Content-Type')).toContain('text/html');
    const html = await res.text();
    expect(html).toContain('Check your email');
    expect(html).toContain('within 7 days, your signature will be deleted');
    expect(html).toContain(`href="${SITE}/writing/pledge"`);
  });
});

describe('sign reply', () => {
  it('says an unconfirmed signature is deleted after the cleanup window', async () => {
    const res = await sign();
    expect(((await res.json()) as { message: string }).message).toBe(
      "Check your email for a link to confirm your signature. If you don't confirm within 7 days, your signature will be deleted.",
    );
  });
});

describe('schema', () => {
  it('holds no IP or user agent column on signatures', async () => {
    const cols = await env.DB.prepare('PRAGMA table_info(signatures)').all<{ name: string }>();
    const names = cols.results.map((c) => c.name);
    expect(names).toEqual(['id', 'petition_slug', 'name', 'email', 'display_consent', 'created_at', 'confirmed_at', 'token_hash', 'updates_consent', 'reminded_at']);
  });

  it('logs email sends by time alone', async () => {
    const cols = await env.DB.prepare('PRAGMA table_info(email_sends)').all<{ name: string }>();
    expect(cols.results.map((c) => c.name)).toEqual(['sent_at']);
  });
});

describe('confirmation reminder', () => {
  const days = (n: number) => new Date(Date.now() + n * 86_400_000);

  it('sends one reminder after 4 days whose new link confirms and whose old link no longer does', async () => {
    await sign({ name: 'Late Signer', updates: true });
    const oldToken = lastToken('confirm');
    await sendReminders(env, days(3.9));
    expect(sentEmails).toHaveLength(1);
    await sendReminders(env, days(4.1));
    expect(sentEmails).toHaveLength(2);
    const mail = sentEmails.at(-1)!;
    expect(mail.subject).toBe('Reminder: confirm your signature: The Pledge');
    expect(mail.text).toMatch(/If it is not confirmed by \d{4}-\d{2}-\d{2}, it will be deleted/);
    expect(mail.text).toContain('Name: Late Signer\nShown on the public list: no\nEmail updates about this campaign: yes');
    await sendReminders(env, days(5));
    expect(sentEmails).toHaveLength(2);
    expect((await post('confirm', oldToken)).status).toBe(400);
    expect((await post('confirm', lastToken('confirm'))).status).toBe(200);
  });

  it('skips confirmed signatures and closed petitions', async () => {
    await signAndConfirm();
    await sendReminders(env, days(5));
    expect(sentEmails).toHaveLength(1);
    await sign();
    await closePetition();
    await sendReminders(env, days(5));
    expect(sentEmails).toHaveLength(2);
  });

  it('starts the 4 days again when an unconfirmed signer signs again', async () => {
    await sign({ email: 'again@example.org' });
    await sendReminders(env, days(5));
    expect(sentEmails.at(-1)!.subject).toMatch(/^Reminder/);
    await env.DB.prepare("UPDATE signatures SET created_at = '2026-01-01T00:00:00.000Z'").run();
    await sign({ email: 'again@example.org' });
    expect(sentEmails.at(-1)!.subject).toMatch(/^Confirm/);
    await sendReminders(env, days(5));
    expect(sentEmails.at(-1)!.subject).toMatch(/^Reminder/);
  });

  it('keeps the first link working and retries next run when the reminder cannot be sent', async () => {
    await sign();
    const firstToken = lastToken('confirm');
    resendStatus = 500;
    await sendReminders(env, days(5));
    resendStatus = 200;
    expect((await post('confirm', firstToken)).status).toBe(200);
  });

  it('retries a failed reminder on the next run', async () => {
    await sign();
    resendStatus = 500;
    await sendReminders(env, days(5));
    resendStatus = 200;
    await sendReminders(env, days(5));
    expect(sentEmails.at(-1)!.subject).toMatch(/^Reminder/);
  });

  it('counts reminders toward the hourly cap', async () => {
    for (let i = 0; i < 3; i++) await sign();
    const later = days(5);
    for (let i = 0; i < HOURLY_EMAIL_CAP - 1; i++) {
      await env.DB.prepare('INSERT INTO email_sends (sent_at) VALUES (?)').bind(later.toISOString()).run();
    }
    await sendReminders(env, later);
    expect(sentEmails.filter((m) => m.subject.startsWith('Reminder'))).toHaveLength(1);
  });
});

describe('daily cleanup', () => {
  it('purges unconfirmed rows after 7 days and keeps confirmed ones', async () => {
    await signAndConfirm();
    await sign();
    await cleanup(env, new Date(Date.now() + 6 * 86_400_000));
    expect(await rowCount()).toBe(2);
    await cleanup(env, new Date(Date.now() + 8 * 86_400_000));
    expect(await rowCount()).toBe(1);
  });

  it('prunes the email send log once it falls outside the cap window', async () => {
    await sign();
    const sends = async () => (await env.DB.prepare('SELECT COUNT(*) AS n FROM email_sends').first<{ n: number }>())!.n;
    await cleanup(env, new Date(Date.now() + 30 * 60_000));
    expect(await sends()).toBe(1);
    await cleanup(env, new Date(Date.now() + 61 * 60_000));
    expect(await sends()).toBe(0);
  });

  it('deletes emails on closed petitions but keeps the signature', async () => {
    await signAndConfirm({ consent: true, name: 'Kept Name' });
    await closePetition();
    await cleanup(env);
    const row = await env.DB.prepare('SELECT name, email FROM signatures').first();
    expect(row).toEqual({ name: 'Kept Name', email: null });
    expect((await publicJson()).body.count).toBe(1);
  });

  it('keeps the email at close only for confirmed signers still asking for updates', async () => {
    await signAndConfirm({ email: 'updates@example.org', updates: true });
    await signAndConfirm({ email: 'quiet@example.org' });
    await sign({ email: 'unconfirmed@example.org', updates: true });
    await signAndConfirm({ email: 'stopped@example.org', updates: true });
    await env.DB.prepare("UPDATE signatures SET updates_consent = 0 WHERE email = 'stopped@example.org'").run();
    await closePetition();
    await cleanup(env);
    const { results } = await env.DB.prepare('SELECT email FROM signatures WHERE email IS NOT NULL').all();
    expect(results).toEqual([{ email: 'updates@example.org' }]);
  });
});

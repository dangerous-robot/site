import { applyD1Migrations, env, reset } from 'cloudflare:test';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import worker, { cleanup } from '../src/index';

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
  consent?: boolean;
  honeypot?: string;
  started?: number;
  json?: boolean;
  ip?: string;
  origin?: string | null;
}

function sign(o: SignOpts = {}): Promise<Response> {
  const body = new URLSearchParams({
    name: o.name ?? 'Ada Lovelace',
    email: o.email ?? `signer${++ipCounter}@example.org`,
    website: o.honeypot ?? '',
    started: String(o.started ?? Date.now() - 10_000),
  });
  if (o.consent) body.set('show_name', 'on');
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
    expect(res.headers.get('Cache-Control')).toBe('public, max-age=60');
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

  it('rejects a missing name or a malformed email', async () => {
    expect((await sign({ name: '  ' })).status).toBe(400);
    expect((await sign({ email: 'not-an-email' })).status).toBe(400);
    expect(await rowCount()).toBe(0);
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
});

describe('repeat signatures', () => {
  it('re-sends with a fresh token while unconfirmed, keeping one row', async () => {
    await sign({ email: 'again@example.org' });
    const first = lastToken('confirm');
    await sign({ email: 'again@example.org' });
    expect(sentEmails).toHaveLength(2);
    expect(await rowCount()).toBe(1);
    expect((await post('confirm', first)).status).toBe(400);
    expect((await post('confirm', lastToken('confirm'))).status).toBe(200);
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
    const res = await sign({ started: Date.now() - 500 });
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

  it('refuses a browser POST from another origin', async () => {
    expect((await sign({ origin: 'https://evil.example' })).status).toBe(403);
    expect(await rowCount()).toBe(0);
  });
});

describe('closed petitions', () => {
  it('refuses new signatures and reports closed status', async () => {
    await env.DB.prepare("UPDATE petitions SET status = 'closed', closed_at = '2026-12-01T00:00:00.000Z'").run();
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
    expect(html).toContain(`${SITE}/writing/pledge#sign`);
  });
});

describe('schema', () => {
  it('holds no IP or user agent column on signatures', async () => {
    const cols = await env.DB.prepare('PRAGMA table_info(signatures)').all<{ name: string }>();
    const names = cols.results.map((c) => c.name);
    expect(names).toEqual(['id', 'petition_slug', 'name', 'email', 'display_consent', 'created_at', 'confirmed_at', 'token_hash']);
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

  it('deletes emails on closed petitions but keeps the signature', async () => {
    await signAndConfirm({ consent: true, name: 'Kept Name' });
    await env.DB.prepare("UPDATE petitions SET status = 'closed', closed_at = '2026-12-01T00:00:00.000Z'").run();
    await cleanup(env);
    const row = await env.DB.prepare('SELECT name, email FROM signatures').first();
    expect(row).toEqual({ name: 'Kept Name', email: null });
    expect((await publicJson()).body.count).toBe(1);
  });
});

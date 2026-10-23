// The Worker may be deployed before migration 0005 (source column, per-domain counts)
// is applied. The web form, cleanup and reminders must keep working on the old schema.
import { applyD1Migrations, env, reset } from 'cloudflare:test';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import worker, { cleanup, sendReminders } from '../src/index';

const API = 'https://api.dangerousrobot.org';
let sent: { text: string }[] = [];

beforeEach(async () => {
  await applyD1Migrations(
    env.DB,
    env.TEST_MIGRATIONS.filter((m) => !m.name.startsWith('0005')),
  );
  await env.DB.prepare(
    "INSERT INTO petitions (slug, title, post_url, status, opened_at) VALUES ('pledge', 'The Pledge', 'https://dangerousrobot.org/writing/pledge', 'open', '2026-10-04T00:00:00.000Z')",
  ).run();
  sent = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (String(input instanceof Request ? input.url : input).includes('siteverify')) {
      return Response.json({ success: true, hostname: 'dangerousrobot.org', action: 'petition-sign' });
    }
    sent.push(JSON.parse(String(init!.body)));
    return new Response('{}');
  });
});

afterEach(async () => {
  vi.restoreAllMocks();
  await reset();
});

function post(path: string, body: Record<string, string>, accept = 'application/json') {
  return worker.fetch(
    new Request(`${API}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: accept, 'CF-Connecting-IP': '10.1.1.1' },
      body: new URLSearchParams(body),
    }),
    env,
  );
}

it('signs, confirms, cleans up and reminds on the schema before 0005', async () => {
  const cols = await env.DB.prepare('PRAGMA table_info(signatures)').all<{ name: string }>();
  expect(cols.results.map((c) => c.name)).not.toContain('source');

  const form = { name: 'Ada', email: 'ada@example.org', 'cf-turnstile-response': 'tok', elapsed: '10000' };
  expect((await post('/petitions/pledge/sign', form)).status).toBe(200);
  expect((await post('/petitions/pledge/sign', { ...form, email: 'late@example.org' })).status).toBe(200);
  const token = /confirm\?t=([0-9a-f]+)/.exec(sent[0].text)![1];
  expect((await post('/petitions/pledge/confirm', { t: token }, 'text/html')).status).toBe(200);
  // The tokenless no-JS page needs no schema change either.
  expect((await post('/petitions/pledge/sign', { name: 'Ada', email: 'x@example.org' }, 'text/html')).status).toBe(200);

  const error = vi.spyOn(console, 'error').mockImplementation(() => {});
  await sendReminders(env, new Date(Date.now() + 5 * 86_400_000));
  expect(sent).toHaveLength(3);
  await cleanup(env, new Date(Date.now() + 11 * 86_400_000));
  const left = await env.DB.prepare('SELECT email FROM signatures').all<{ email: string }>();
  expect(left.results.map((r) => r.email)).toEqual(['ada@example.org']);
  error.mockRestore();
});

import type { Env } from './env';
import { confirmationEmail, sendEmail } from './email';
import { actionPage, messagePage } from './pages';

const MIN_FILL_MS = 3000;
// An unconfirmed address gets at most one confirmation email per window, so the
// form cannot be used to flood someone else's inbox.
const RESEND_WINDOW_MS = 10 * 60_000;
// Site-wide ceiling on confirmation emails per window, re-sends included. The
// per-IP limiter counts per Cloudflare machine, so a script opening fresh
// connections slips past it; this cap bounds how much mail the form can send.
export const HOURLY_EMAIL_CAP = 30;
const CAP_WINDOW_MS = 60 * 60_000;
// 10 rather than 7 while runs missed during a Cloudflare cron outage catch up (UNSCHEDULED.md).
const UNCONFIRMED_TTL_DAYS = 10;
const REMINDER_AFTER_DAYS = 4;
// Each reminder is one Resend call; the Workers Free plan allows 50 outside calls per run.
// Leftovers go out on the next daily run.
const REMINDERS_PER_RUN = 20;
const DAY_MS = 86_400_000;
const NAME_MAX = 100;
const EMAIL_MAX = 254;
const SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';
// Turnstile's documented token limit; anything longer is not a real token.
const TURNSTILE_TOKEN_MAX = 2048;
const SITEVERIFY_TIMEOUT_MS = 5000;

interface Petition {
  slug: string;
  title: string;
  post_url: string;
  status: 'open' | 'closed';
  closed_at: string | null;
}

const ROUTE = /^\/petitions\/([a-z0-9-]+)(?:\/(sign|confirm|remove))?\/?$/;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const match = ROUTE.exec(url.pathname);
    if (!match) return new Response('Not found', { status: 404 });
    const [, slug, action] = match;
    const method = request.method;

    if (!action && method === 'GET') return getPetition(request, env, slug);
    if (action === 'sign' && method === 'POST') return sign(request, env, slug);
    if (action === 'confirm' || action === 'remove') {
      if (method === 'GET') return tokenLanding(env, slug, action, url.searchParams.get('t'));
      if (method === 'POST') return action === 'confirm' ? confirm(request, env, slug) : remove(request, env, slug);
    }
    return new Response('Method not allowed', { status: 405 });
  },

  async scheduled(_controller: ScheduledController, env: Env): Promise<void> {
    await cleanup(env);
    await sendReminders(env);
  },
};

export async function cleanup(env: Env, now = new Date()): Promise<void> {
  const cutoff = new Date(now.getTime() - UNCONFIRMED_TTL_DAYS * DAY_MS).toISOString();
  await env.DB.batch([
    env.DB.prepare('DELETE FROM signatures WHERE confirmed_at IS NULL AND created_at < ?').bind(cutoff),
    env.DB.prepare('DELETE FROM email_sends WHERE sent_at < ?').bind(new Date(now.getTime() - CAP_WINDOW_MS).toISOString()),
    // Update recipients (migration 0004) keep their email until they opt out.
    env.DB.prepare(
      `UPDATE signatures SET email = NULL
       WHERE email IS NOT NULL AND petition_slug IN (SELECT slug FROM petitions WHERE status = 'closed')
         AND id NOT IN (SELECT id FROM update_recipients)`,
    ),
  ]);
}

interface DueReminder {
  id: number;
  petition_slug: string;
  title: string;
  name: string;
  email: string;
  display_consent: number;
  updates_consent: number;
  created_at: string;
  token_hash: string;
}

/**
 * Reminds each unconfirmed signer once, REMINDER_AFTER_DAYS after signing. Tokens are stored
 * hashed, so the reminder carries fresh links; they are saved only after the send, so a failed
 * or interrupted run leaves the first links working. Each reminder follows a sign-up that
 * already passed the hourly cap, so the cap does not apply here.
 */
export async function sendReminders(env: Env, now = new Date()): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT s.id, s.petition_slug, p.title, s.name, s.email, s.display_consent, s.updates_consent, s.created_at, s.token_hash
     FROM signatures s JOIN petitions p ON p.slug = s.petition_slug
     WHERE s.confirmed_at IS NULL AND s.reminded_at IS NULL AND s.email IS NOT NULL
       AND p.status = 'open' AND s.created_at < ?
     ORDER BY s.created_at LIMIT ?`,
  )
    .bind(new Date(now.getTime() - REMINDER_AFTER_DAYS * DAY_MS).toISOString(), REMINDERS_PER_RUN)
    .all<DueReminder>();

  const saves: D1PreparedStatement[] = [];
  for (const row of results) {
    const token = newToken();
    try {
      await sendEmail(
        env,
        confirmationEmail({
          to: row.email,
          title: row.title,
          name: row.name,
          showName: row.display_consent === 1,
          wantsUpdates: row.updates_consent === 1,
          ...tokenLinks(env, row.petition_slug, token),
          reminderDaysLeft: UNCONFIRMED_TTL_DAYS - Math.floor((now.getTime() - Date.parse(row.created_at)) / DAY_MS),
        }),
      );
    } catch (err) {
      console.error(err);
      continue;
    }
    // Matching the old hash means a confirm or re-sign since the SELECT wins; its links stay.
    saves.push(
      env.DB.prepare('UPDATE signatures SET token_hash = ?, reminded_at = ? WHERE id = ? AND token_hash = ? AND confirmed_at IS NULL')
        .bind(await sha256(token), now.toISOString(), row.id, row.token_hash),
    );
  }
  if (saves.length > 0) await env.DB.batch(saves);
}

async function getPetition(request: Request, env: Env, slug: string): Promise<Response> {
  const [petitions, count, names] = await env.DB.batch([
    petitionQuery(env, slug),
    env.DB.prepare('SELECT COUNT(*) AS n FROM signatures WHERE petition_slug = ? AND confirmed_at IS NOT NULL').bind(slug),
    env.DB.prepare(
      'SELECT name FROM signatures WHERE petition_slug = ? AND confirmed_at IS NOT NULL AND display_consent = 1 ORDER BY confirmed_at DESC, id DESC',
    ).bind(slug),
  ]);
  const petition = petitions.results[0] as Petition | undefined;
  if (!petition) return json(request, env, { ok: false, error: 'No such petition.' }, 404);
  return json(
    request,
    env,
    {
      slug: petition.slug,
      title: petition.title,
      status: petition.status,
      closed_at: petition.closed_at,
      count: (count.results[0] as { n: number }).n,
      names: (names.results as { name: string }[]).map((r) => r.name),
    },
    200,
  );
}

async function sign(request: Request, env: Env, slug: string): Promise<Response> {
  const origin = request.headers.get('Origin');
  if (origin && !allowedOrigins(env).includes(origin)) return reply(request, env, 403, 'Signing is only possible from dangerousrobot.org.', null);

  const petition = await loadPetition(env, slug);
  if (!petition) return reply(request, env, 404, 'No such petition.', null);

  const { success } = await env.SIGN_LIMITER.limit({ key: request.headers.get('CF-Connecting-IP') ?? 'unknown' });
  if (!success) return reply(request, env, 429, 'Too many attempts. Please try again in a minute.', petition.post_url);

  const form = await readForm(request);
  if (!form) return reply(request, env, 400, 'The form could not be read. Please try again.', petition.post_url);
  const field = (k: string) => String(form.get(k) ?? '').trim();
  const checkEmail = () =>
    reply(
      request,
      env,
      200,
      `Check your email for a link to confirm your signature. If you don't confirm within ${UNCONFIRMED_TTL_DAYS} days, your signature will be deleted.`,
      petition.post_url,
      'Check your email',
    );

  // Bots get the same answer as people, so they learn nothing from it.
  if (field('website') !== '') return checkEmail();
  // Milliseconds the page was open, measured by the browser's own monotonic clock
  // (not compared against ours, so a skewed client clock cannot drop a signer).
  // Absent means no page script set it; the bot check below still applies.
  const elapsed = Number(field('elapsed'));
  if (elapsed > 0 && elapsed < MIN_FILL_MS) return checkEmail();

  if (petition.status === 'closed') return reply(request, env, 409, closedText(petition), petition.post_url);

  const name = field('name').replace(/\s+/g, ' ');
  const email = field('email').toLowerCase();
  if (!name || name.length > NAME_MAX || /[\u0000-\u001f]/.test(name)) {
    return reply(request, env, 400, `Please enter your name (up to ${NAME_MAX} characters).`, petition.post_url);
  }
  // Plain addresses only. A looser check let `"x"<victim@...>` and `<victim@...>`
  // through as distinct emails that a mail API could deliver to the same inbox,
  // and let shell metacharacters reach the runbook's removal command.
  if (email.length > EMAIL_MAX || !/^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(email)) {
    return reply(request, env, 400, 'Please enter a valid email address.', petition.post_url);
  }
  // A checked box sends "on"; anything else (absent, empty, "0") is no consent.
  const showName = form.get('show_name') === 'on';
  const wantsUpdates = form.get('updates') === 'on';

  // After the field checks, so a typo does not spend the single-use token; before the
  // cap, the insert and the email, so a script without a passing check sends nothing.
  const check = await verifyTurnstile(env, field('cf-turnstile-response'), request.headers.get('CF-Connecting-IP'));
  if (check === 'missing') {
    const message = (request.headers.get('Accept') ?? '').includes('application/json')
      ? 'The bot check has not finished. Please wait for it, or reload the page, then press Sign again.'
      : 'Signing needs JavaScript, for a bot check that stops scripts from signing up other people\'s email addresses. Please turn on JavaScript and sign again, or write to contact@dangerousrobot.org.';
    return reply(request, env, 403, message, petition.post_url);
  }
  if (check === 'failed') {
    return reply(request, env, 403, 'The bot check did not pass. Please reload the page and try again.', petition.post_url);
  }
  if (check === 'error') {
    return reply(request, env, 503, 'We could not run the bot check. Please try again in a minute.', petition.post_url);
  }

  // Concurrent requests can overshoot by a few; close enough for a ceiling.
  const now = Date.now();
  const recent = await env.DB.prepare('SELECT COUNT(*) AS n FROM email_sends WHERE sent_at > ?')
    .bind(new Date(now - CAP_WINDOW_MS).toISOString())
    .first<{ n: number }>();
  if (recent!.n >= HOURLY_EMAIL_CAP) {
    return reply(request, env, 429, 'A lot of people are signing right now. Please try again in an hour.', petition.post_url);
  }

  const token = newToken();
  // A repeat signature from an unconfirmed address gets a fresh token and email,
  // unless one went out within RESEND_WINDOW_MS. A confirmed address is left
  // alone. Every case gets the same reply, so the form never reveals who has signed.
  const row = await env.DB.prepare(
    `INSERT INTO signatures (petition_slug, name, email, display_consent, updates_consent, created_at, token_hash)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (petition_slug, email) DO UPDATE SET
       name = excluded.name, display_consent = excluded.display_consent, updates_consent = excluded.updates_consent,
       created_at = excluded.created_at, token_hash = excluded.token_hash, reminded_at = NULL
     WHERE signatures.confirmed_at IS NULL AND signatures.created_at < ?
     RETURNING id`,
  )
    .bind(slug, name, email, showName ? 1 : 0, wantsUpdates ? 1 : 0, new Date(now).toISOString(), await sha256(token), new Date(now - RESEND_WINDOW_MS).toISOString())
    .first<{ id: number }>();

  if (row) {
    try {
      await sendEmail(env, confirmationEmail({ to: email, title: petition.title, name, showName, wantsUpdates, ...tokenLinks(env, slug, token) }));
    } catch (err) {
      console.error(err);
      // Drop the row so an immediate retry is not swallowed by the resend window.
      await env.DB.prepare('DELETE FROM signatures WHERE id = ?').bind(row.id).run();
      return reply(request, env, 502, 'We could not send the confirmation email. Please try again later.', petition.post_url);
    }
    await env.DB.prepare('INSERT INTO email_sends (sent_at) VALUES (?)').bind(new Date(now).toISOString()).run();
  }
  return checkEmail();
}

/**
 * Asks Turnstile whether the widget's token is genuine. Fails closed: a missing secret,
 * a network error, a timeout or an unreadable answer all refuse the signature. Logs
 * carry error codes only, never the token or the secret.
 */
async function verifyTurnstile(env: Env, token: string, ip: string | null): Promise<'ok' | 'missing' | 'failed' | 'error'> {
  if (!token) return 'missing';
  if (token.length > TURNSTILE_TOKEN_MAX) return 'failed';
  if (!env.TURNSTILE_SECRET_KEY) {
    console.error('turnstile: TURNSTILE_SECRET_KEY is not set; refusing to sign');
    return 'error';
  }
  const body = new URLSearchParams({ secret: env.TURNSTILE_SECRET_KEY, response: token });
  if (ip) body.set('remoteip', ip);
  try {
    const res = await fetch(SITEVERIFY_URL, { method: 'POST', body, signal: AbortSignal.timeout(SITEVERIFY_TIMEOUT_MS) });
    if (!res.ok) {
      console.error(`turnstile: siteverify returned ${res.status}`);
      return 'error';
    }
    const result = (await res.json()) as { success?: unknown; 'error-codes'?: unknown };
    if (result.success === true) return 'ok';
    console.warn(`turnstile: token rejected ${JSON.stringify(result['error-codes'] ?? [])}`);
    return 'failed';
  } catch (err) {
    console.error(`turnstile: siteverify unreachable (${err instanceof Error ? err.name : 'unknown error'})`);
    return 'error';
  }
}

async function tokenLanding(env: Env, slug: string, action: 'confirm' | 'remove', token: string | null): Promise<Response> {
  const petition = await loadPetition(env, slug);
  if (!petition) return notFoundPage();
  if (!token) return messagePage('Link incomplete', 'This link is missing its code. Please use the full link from your email.', petition.post_url, 400);
  const [verb, change] = action === 'confirm' ? ['Confirm', 'add your signature to'] : ['Remove', 'remove your signature from'];
  return actionPage(
    `${verb} your signature`,
    `Press the button to ${change} "${petition.title}".`,
    `/petitions/${slug}/${action}`,
    token,
    `${verb} my signature`,
    petition.post_url,
  );
}

async function confirm(request: Request, env: Env, slug: string): Promise<Response> {
  const petition = await loadPetition(env, slug);
  if (!petition) return notFoundPage();
  const tokenHash = await formTokenHash(request);
  const sig = tokenHash
    ? await env.DB.prepare('SELECT id, confirmed_at FROM signatures WHERE petition_slug = ? AND token_hash = ?')
        .bind(slug, tokenHash)
        .first<{ id: number; confirmed_at: string | null }>()
    : null;
  if (!sig) return invalidLink(petition);
  let confirmedAt = sig.confirmed_at;
  if (!confirmedAt) {
    if (petition.status === 'closed') return messagePage('Petition closed', closedText(petition), petition.post_url, 409);
    // COALESCE keeps the first timestamp if a concurrent confirm (a link scanner) won the race.
    const updated = await env.DB.prepare('UPDATE signatures SET confirmed_at = COALESCE(confirmed_at, ?) WHERE id = ? RETURNING confirmed_at')
      .bind(new Date().toISOString(), sig.id)
      .first<{ confirmed_at: string }>();
    if (!updated) return invalidLink(petition);
    confirmedAt = updated.confirmed_at;
  }
  // Rank among confirmed signatures, so reloading the thank-you page shows the same number.
  const rank = await env.DB.prepare(
    `SELECT COUNT(*) AS n FROM signatures
     WHERE petition_slug = ? AND confirmed_at IS NOT NULL
       AND (confirmed_at < ? OR (confirmed_at = ? AND id <= ?))`,
  )
    .bind(slug, confirmedAt, confirmedAt, sig.id)
    .first<{ n: number }>();
  return messagePage('Thank you', `Your signature is confirmed. You are signatory ${rank!.n}.`, petition.post_url);
}

async function remove(request: Request, env: Env, slug: string): Promise<Response> {
  const petition = await loadPetition(env, slug);
  if (!petition) return notFoundPage();
  const tokenHash = await formTokenHash(request);
  const removed = tokenHash
    ? await env.DB.prepare('DELETE FROM signatures WHERE petition_slug = ? AND token_hash = ? RETURNING id').bind(slug, tokenHash).first()
    : null;
  if (!removed) return invalidLink(petition);
  return messagePage('Signature removed', 'Your signature is removed.', petition.post_url);
}

async function formTokenHash(request: Request): Promise<string | null> {
  const token = String((await readForm(request))?.get('t') ?? '');
  return token ? sha256(token) : null;
}

/** null when the body is missing or not a form; formData() throws on those. */
async function readForm(request: Request): Promise<FormData | null> {
  try {
    return await request.formData();
  } catch {
    return null;
  }
}

function notFoundPage(): Response {
  return messagePage('Not found', 'No such petition.', null, 404);
}

function invalidLink(petition: Petition): Response {
  return messagePage(
    'Link not valid',
    [
      `This link does not match a signature. Usually a newer email from us has replaced it: the reminder we send ${REMINDER_AFTER_DAYS} days after signing, or the email sent when you signed again.`,
      `To fix it, use the link in our most recent email. If you cannot find it, sign the petition again with the same email address and we will send you a new email with a link to confirm your signature and a link to remove it. Your signature still counts only once. We send at most one email to an address every ${RESEND_WINDOW_MS / 60_000} minutes, so if you just signed, wait a few minutes first.`,
      'If you already confirmed or removed your signature, there is nothing more to do.',
    ],
    petition.post_url,
    400,
  );
}

function closedText(p: Petition): string {
  const date = p.closed_at ? ` on ${p.closed_at.slice(0, 10)}` : '';
  return `This petition closed${date} and no longer accepts signatures.`;
}

function petitionQuery(env: Env, slug: string): D1PreparedStatement {
  return env.DB.prepare('SELECT slug, title, post_url, status, closed_at FROM petitions WHERE slug = ?').bind(slug);
}

function loadPetition(env: Env, slug: string): Promise<Petition | null> {
  return petitionQuery(env, slug).first<Petition>();
}

function allowedOrigins(env: Env): string[] {
  return env.ALLOWED_ORIGINS.split(',').map((s) => s.trim());
}

function corsHeaders(request: Request, env: Env): Record<string, string> {
  const origin = request.headers.get('Origin');
  if (!origin || !allowedOrigins(env).includes(origin)) return { Vary: 'Origin' };
  return { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' };
}

// no-store: a signer returning from the confirm page must see the new count.
function json(request: Request, env: Env, body: unknown, status: number): Response {
  return Response.json(body, { status, headers: { 'Cache-Control': 'no-store', ...corsHeaders(request, env) } });
}

/** JSON for the site's fetch; a full page for a plain no-JS form POST. */
function reply(request: Request, env: Env, status: number, message: string, postUrl: string | null, heading?: string): Response {
  if ((request.headers.get('Accept') ?? '').includes('application/json')) {
    return json(request, env, status === 200 ? { ok: true, message } : { ok: false, error: message }, status);
  }
  return messagePage(heading ?? (status === 200 ? 'Thank you' : 'Something went wrong'), message, postUrl, status);
}

function tokenLinks(env: Env, slug: string, token: string): { confirmUrl: string; removeUrl: string } {
  const base = `${env.API_ORIGIN}/petitions/${slug}`;
  return { confirmUrl: `${base}/confirm?t=${token}`, removeUrl: `${base}/remove?t=${token}` };
}

function newToken(): string {
  return toHex(crypto.getRandomValues(new Uint8Array(32)));
}

function toHex(bytes: Uint8Array): string {
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function sha256(s: string): Promise<string> {
  return toHex(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))));
}

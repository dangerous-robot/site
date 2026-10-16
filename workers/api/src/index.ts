import type { Env } from './env';
import { confirmationEmail, notSignedEmail, receiptEmail, sendEmail, type Email } from './email';
import {
  buildSubject,
  cloudflareDmarc,
  decodeEncodedWords,
  isAutoSubmitted,
  isPlainAddress,
  parseFrom,
  parseHeaders,
  parseSubject,
  readHeaderBlock,
} from './inbound';
import { actionPage, lastStepPage, messagePage } from './pages';

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
const SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';
// Turnstile's documented token limit; anything longer is not a real token.
const TURNSTILE_TOKEN_MAX = 2048;
export const SITEVERIFY_TIMEOUT_MS = 5000;
// What a genuine token from the live sign form reports; the form sets the action.
const TURNSTILE_HOSTNAME = 'dangerousrobot.org';
const TURNSTILE_ACTION = 'petition-sign';
// Messages to sign@ acted on per sender domain per UTC day. Anyone who owns a domain can
// mint addresses that pass DMARC; this bounds the signatures and replies one domain gets.
export const DOMAIN_DAILY_CAP = 20;
// Large mailbox providers, where one domain is millions of separate people.
const CAP_EXEMPT_DOMAINS = new Set([
  'gmail.com', 'googlemail.com', 'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
  'icloud.com', 'me.com', 'mac.com', 'yahoo.com', 'proton.me', 'protonmail.com', 'pm.me',
]);
const NOT_VERIFIED = 'We could not confirm this message came from your address. Write to contact@dangerousrobot.org.';
const DOMAIN_CAPPED = 'Too many messages from your domain today. Please try again tomorrow, or write to contact@dangerousrobot.org.';

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

  // Messages to sign@dangerousrobot.org, routed here by an Email Routing rule.
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    // Outcome codes only: Workers Logs is on, and the privacy page promises name, email and consents only.
    console.log(`email-sign: ${await signByEmail(message, env)}`);
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
  // Apart from the batch above, so the web cleanup still runs if migration 0005 is not applied yet.
  try {
    await env.DB.prepare('DELETE FROM email_in_counts WHERE day < ?').bind(utcDay(now)).run();
  } catch {
    console.error('cleanup: could not prune email_in_counts');
  }
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
  if (!isPlainAddress(email)) {
    return reply(request, env, 400, 'Please enter a valid email address.', petition.post_url);
  }
  // A checked box sends "on"; anything else (absent, empty, "0") is no consent.
  const showName = form.get('show_name') === 'on';
  const wantsUpdates = form.get('updates') === 'on';

  // After the field checks, so a typo does not spend the single-use token; before the
  // cap, the insert and the email, so a script without a passing check sends nothing.
  const check = await verifyTurnstile(env, field('cf-turnstile-response'), request.headers.get('CF-Connecting-IP'));
  if (check === 'missing') {
    // A plain form POST with no token is a reader without JS: offer to sign by email.
    // Nothing is stored or sent until a message from their address arrives.
    if (!(request.headers.get('Accept') ?? '').includes('application/json')) {
      return lastStepPage(buildSubject({ slug, name, showName, wantsUpdates }), petition.post_url);
    }
    return reply(request, env, 403, 'The bot check has not finished. Please wait for it, or reload the page, then press Sign again.', petition.post_url);
  }
  if (check === 'failed') {
    return reply(request, env, 403, 'The bot check did not pass. Please reload the page and try again.', petition.post_url);
  }
  if (check === 'error') {
    return reply(request, env, 503, 'We could not run the bot check. Please try again in a minute.', petition.post_url);
  }

  // Concurrent requests can overshoot by a few; close enough for a ceiling.
  const now = Date.now();
  if (await hourlyCapReached(env, now)) {
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

function hourlyCapReached(env: Env, now: number): Promise<boolean> {
  return env.DB.prepare('SELECT COUNT(*) AS n FROM email_sends WHERE sent_at > ?')
    .bind(new Date(now - CAP_WINDOW_MS).toISOString())
    .first<{ n: number }>()
    .then((r) => r!.n >= HOURLY_EMAIL_CAP);
}

/**
 * Signs from a message to sign@ whose From domain passed DMARC by Cloudflare's own check.
 * Order matters: the sender check comes first, the caps come before any reply, and every
 * reply goes to the From address that just passed. Returns the outcome code for the log
 * (ok, no-auth-header, bad-from, dmarc-fail, auto, capped, unknown-petition, closed,
 * no-name), plus `reply=sent|capped|failed` when a reply was attempted.
 */
export async function signByEmail(message: ForwardableEmailMessage, env: Env, now = new Date()): Promise<string> {
  const block = await readHeaderBlock(message.raw);
  const headers = block === null ? [] : parseHeaders(block);
  const auth = cloudflareDmarc(headers);
  if (!auth) {
    message.setReject(NOT_VERIFIED);
    return 'no-auth-header';
  }
  // The header From, not message.from (the envelope sender), is what the signer sees and DMARC covers.
  const from = parseFrom(headers);
  if (!from) {
    message.setReject(NOT_VERIFIED);
    return 'bad-from';
  }
  const domain = from.address.slice(from.address.indexOf('@') + 1);
  if (auth.result !== 'pass' || auth.headerFrom !== domain) {
    message.setReject(NOT_VERIFIED);
    return 'dmarc-fail';
  }
  if (isAutoSubmitted(headers)) return 'auto';

  if (!CAP_EXEMPT_DOMAINS.has(domain)) {
    // Counted before acting, so a domain over the cap gets neither a signature nor a reply.
    const count = await env.DB.prepare(
      `INSERT INTO email_in_counts (day, domain_hash, n) VALUES (?, ?, 1)
       ON CONFLICT (day, domain_hash) DO UPDATE SET n = n + 1 RETURNING n`,
    )
      .bind(utcDay(now), await sha256(domain))
      .first<{ n: number }>();
    if (count!.n > DOMAIN_DAILY_CAP) {
      message.setReject(DOMAIN_CAPPED);
      return 'capped';
    }
  }

  const answer = async (outcome: string, mail: Email) => `${outcome} reply=${await sendCapped(env, mail, now)}`;
  const subjectHeader = headers.find((h) => h.name.toLowerCase() === 'subject')?.value ?? '';
  const subject = parseSubject(decodeEncodedWords(subjectHeader));
  const petition = subject ? await loadPetition(env, subject.slug) : null;
  if (!subject || !petition) {
    return answer(
      'unknown-petition',
      notSignedEmail(
        from.address,
        'We could not find that petition',
        'We could not tell which petition your email to sign@dangerousrobot.org is for. Please start from the petition page on dangerousrobot.org: its Sign button fills in the subject line for you.',
      ),
    );
  }
  if (petition.status === 'closed') {
    return answer('closed', notSignedEmail(from.address, `Petition closed: ${petition.title}`, closedText(petition)));
  }
  const name = [subject.name, from.displayName].map((n) => n.replace(/\s+/g, ' ').trim()).find(validName);
  if (!name) {
    return answer(
      'no-name',
      notSignedEmail(
        from.address,
        `Your name is needed: ${petition.title}`,
        `Your email reached us, but we could not find your name in the subject line or on your address. Please send it again with your name in the subject, like this: Sign ${petition.slug} | Name: Your Name | Show my name: no | Updates: no (up to ${NAME_MAX} characters).`,
      ),
    );
  }

  // A new row is confirmed at once (the message proved the address). An unconfirmed web row
  // is confirmed and takes the emailed name and choices; a confirmed row keeps its data.
  // The token hash of an existing row is left alone here: its removal link must keep
  // working unless the receipt with the new link actually goes out.
  const token = newToken();
  const tokenHash = await sha256(token);
  const at = now.toISOString();
  type Sig = { id: number; token_hash: string; name: string; display_consent: number; updates_consent: number };
  const sig =
    (await env.DB.prepare(
      `INSERT INTO signatures (petition_slug, name, email, display_consent, updates_consent, created_at, confirmed_at, token_hash, source)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'email')
       ON CONFLICT (petition_slug, email) DO UPDATE SET
         name = excluded.name, display_consent = excluded.display_consent, updates_consent = excluded.updates_consent,
         confirmed_at = excluded.confirmed_at, source = 'email'
       WHERE signatures.confirmed_at IS NULL
       RETURNING id, token_hash, name, display_consent, updates_consent`,
    )
      .bind(petition.slug, name, from.address, subject.showName ? 1 : 0, subject.wantsUpdates ? 1 : 0, at, at, tokenHash)
      .first<Sig>()) ??
    (await env.DB.prepare('SELECT id, token_hash, name, display_consent, updates_consent FROM signatures WHERE petition_slug = ? AND email = ?')
      .bind(petition.slug, from.address)
      .first<Sig>());
  if (!sig) return 'ok reply=none';

  const sent = await sendCapped(
    env,
    receiptEmail({
      to: from.address,
      title: petition.title,
      name: sig.name,
      showName: sig.display_consent === 1,
      wantsUpdates: sig.updates_consent === 1,
      removeUrl: tokenLinks(env, petition.slug, token).removeUrl,
    }),
    now,
  );
  if (sent === 'sent' && sig.token_hash !== tokenHash) {
    await env.DB.prepare('UPDATE signatures SET token_hash = ? WHERE id = ? AND token_hash = ?').bind(tokenHash, sig.id, sig.token_hash).run();
  }
  return `ok reply=${sent}`;
}

function validName(name: string): boolean {
  return name !== '' && name.length <= NAME_MAX && !/[\u0000-\u001f]/.test(name);
}

/**
 * Sends one reply under the site-wide hourly cap, logging it in email_sends like the web
 * form's emails. Never logs the error: Resend's error text can carry the address.
 */
async function sendCapped(env: Env, mail: Email, now: Date): Promise<'sent' | 'capped' | 'failed'> {
  if (await hourlyCapReached(env, now.getTime())) return 'capped';
  try {
    await sendEmail(env, mail);
  } catch {
    return 'failed';
  }
  await env.DB.prepare('INSERT INTO email_sends (sent_at) VALUES (?)').bind(now.toISOString()).run();
  return 'sent';
}

function utcDay(d: Date): string {
  return d.toISOString().slice(0, 10);
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
    const result = (await res.json()) as { success?: unknown; 'error-codes'?: unknown; hostname?: unknown; action?: unknown };
    if (result.success !== true) {
      console.warn(`turnstile: token rejected ${JSON.stringify(result['error-codes'] ?? [])}`);
      return 'failed';
    }
    // A token solved on another site, or for another widget on this key, is not a sign-up.
    const hostname = env.TURNSTILE_HOSTNAME ?? TURNSTILE_HOSTNAME;
    const action = env.TURNSTILE_ACTION ?? TURNSTILE_ACTION;
    if (result.hostname !== hostname || (result.action ?? '') !== action) {
      console.warn(`turnstile: token for ${JSON.stringify(result.hostname)} / ${JSON.stringify(result.action)} refused`);
      return 'failed';
    }
    return 'ok';
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

import type { Env } from './env';
import { confirmationEmail, sendEmail } from './email';
import { actionPage, messagePage } from './pages';

const MIN_FILL_MS = 3000;
// An unconfirmed address gets at most one confirmation email per window, so the
// form cannot be used to flood someone else's inbox.
const RESEND_WINDOW_MS = 10 * 60_000;
const UNCONFIRMED_TTL_DAYS = 7;
const NAME_MAX = 100;
const EMAIL_MAX = 254;

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
  },
};

export async function cleanup(env: Env, now = new Date()): Promise<void> {
  const cutoff = new Date(now.getTime() - UNCONFIRMED_TTL_DAYS * 86_400_000).toISOString();
  await env.DB.batch([
    env.DB.prepare('DELETE FROM signatures WHERE confirmed_at IS NULL AND created_at < ?').bind(cutoff),
    env.DB.prepare(
      "UPDATE signatures SET email = NULL WHERE email IS NOT NULL AND petition_slug IN (SELECT slug FROM petitions WHERE status = 'closed')",
    ),
  ]);
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

  const form = await request.formData();
  const field = (k: string) => String(form.get(k) ?? '').trim();
  const checkEmail = () => reply(request, env, 200, 'Check your email for a link to confirm your signature.', petition.post_url, 'Check your email');

  // Bots get the same answer as people, so they learn nothing from it.
  if (field('website') !== '') return checkEmail();
  // Milliseconds the page was open, measured by the browser's own monotonic clock
  // (not compared against ours, so a skewed client clock cannot drop a signer).
  // Absent for the no-JS form, which is accepted.
  const elapsed = Number(field('elapsed'));
  if (elapsed > 0 && elapsed < MIN_FILL_MS) return checkEmail();

  if (petition.status === 'closed') return reply(request, env, 409, closedText(petition), petition.post_url);

  const name = field('name').replace(/\s+/g, ' ');
  const email = field('email').toLowerCase();
  if (!name || name.length > NAME_MAX || /[\u0000-\u001f]/.test(name)) {
    return reply(request, env, 400, `Please enter your name (up to ${NAME_MAX} characters).`, petition.post_url);
  }
  if (email.length > EMAIL_MAX || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return reply(request, env, 400, 'Please enter a valid email address.', petition.post_url);
  }
  const consent = form.get('show_name') ? 1 : 0;

  const token = toHex(crypto.getRandomValues(new Uint8Array(32)));
  // A repeat signature from an unconfirmed address gets a fresh token and email,
  // unless one went out within RESEND_WINDOW_MS. A confirmed address is left
  // alone. Every case gets the same reply, so the form never reveals who has signed.
  const now = Date.now();
  const row = await env.DB.prepare(
    `INSERT INTO signatures (petition_slug, name, email, display_consent, created_at, token_hash)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT (petition_slug, email) DO UPDATE SET
       name = excluded.name, display_consent = excluded.display_consent,
       created_at = excluded.created_at, token_hash = excluded.token_hash
     WHERE signatures.confirmed_at IS NULL AND signatures.created_at < ?
     RETURNING id`,
  )
    .bind(slug, name, email, consent, new Date(now).toISOString(), await sha256(token), new Date(now - RESEND_WINDOW_MS).toISOString())
    .first<{ id: number }>();

  if (row) {
    const base = `${new URL(request.url).origin}/petitions/${slug}`;
    try {
      await sendEmail(env, confirmationEmail(email, petition.title, `${base}/confirm?t=${token}`, `${base}/remove?t=${token}`));
    } catch (err) {
      console.error(err);
      return reply(request, env, 502, 'We could not send the confirmation email. Please try again later.', petition.post_url);
    }
  }
  return checkEmail();
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
  if (!sig.confirmed_at) {
    if (petition.status === 'closed') return messagePage('Petition closed', closedText(petition), petition.post_url, 409);
    sig.confirmed_at = new Date().toISOString();
    await env.DB.prepare('UPDATE signatures SET confirmed_at = ? WHERE id = ? AND confirmed_at IS NULL').bind(sig.confirmed_at, sig.id).run();
  }
  // Rank among confirmed signatures, so reloading the thank-you page shows the same number.
  const rank = await env.DB.prepare(
    `SELECT COUNT(*) AS n FROM signatures
     WHERE petition_slug = ? AND confirmed_at IS NOT NULL
       AND (confirmed_at < ? OR (confirmed_at = ? AND id <= ?))`,
  )
    .bind(slug, sig.confirmed_at, sig.confirmed_at, sig.id)
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
  const token = String((await request.formData()).get('t') ?? '');
  return token ? sha256(token) : null;
}

function notFoundPage(): Response {
  return messagePage('Not found', 'No such petition.', null, 404);
}

function invalidLink(petition: Petition): Response {
  return messagePage('Link not valid', 'This link does not match a signature. It may already have been removed.', petition.post_url, 400);
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

function toHex(bytes: Uint8Array): string {
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function sha256(s: string): Promise<string> {
  return toHex(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))));
}

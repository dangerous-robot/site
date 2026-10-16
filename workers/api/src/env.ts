export interface Env {
  DB: D1Database;
  SIGN_LIMITER: RateLimit;
  RESEND_API_KEY?: string;
  /** Turnstile widget secret for siteverify. Unset means every sign attempt is refused. */
  TURNSTILE_SECRET_KEY?: string;
  /** Comma-separated origins allowed to call the API from a browser. */
  ALLOWED_ORIGINS: string;
  /** Base of the links in emails, e.g. https://api.dangerousrobot.org. */
  API_ORIGIN: string;
  MAIL_FROM: string;
  MAIL_REPLY_TO: string;
  /** "log" prints emails instead of sending them (wrangler dev). */
  EMAIL_MODE: 'resend' | 'log';
}

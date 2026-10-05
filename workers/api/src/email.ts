import type { Env } from './env';

export interface Email {
  to: string;
  subject: string;
  text: string;
}

export async function sendEmail(env: Env, email: Email): Promise<void> {
  if (env.EMAIL_MODE === 'log') {
    console.log(`[email to ${email.to}] ${email.subject}\n${email.text}`);
    return;
  }
  // Plain text only: no HTML means no tracking pixels or rewritten links.
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: env.MAIL_FROM,
      to: [email.to],
      reply_to: env.MAIL_REPLY_TO,
      subject: email.subject,
      text: email.text,
    }),
  });
  if (!res.ok) {
    throw new Error(`Resend returned ${res.status}: ${await res.text()}`);
  }
}

export function confirmationEmail(to: string, title: string, confirmUrl: string, removeUrl: string): Email {
  return {
    to,
    subject: `Confirm your signature: ${title}`,
    text: [
      `Someone, hopefully you, signed "${title}" on dangerousrobot.org with this email address.`,
      '',
      'Confirm your signature:',
      confirmUrl,
      '',
      'Remove your signature, now or any time later:',
      removeUrl,
      '',
      'If you did not sign, ignore this email and the signature will not be counted.',
      '',
      'Dangerous Robot',
    ].join('\n'),
  };
}

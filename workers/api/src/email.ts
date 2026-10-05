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

export interface ConfirmationDetails {
  to: string;
  title: string;
  name: string;
  showName: boolean;
  confirmUrl: string;
  removeUrl: string;
}

export function confirmationEmail({ to, title, name, showName, confirmUrl, removeUrl }: ConfirmationDetails): Email {
  return {
    to,
    subject: `Confirm your signature: ${title}`,
    text: [
      `Someone, hopefully you, signed "${title}" on dangerousrobot.org with this email address.`,
      '',
      `Name: ${name}`,
      `Shown on the public list: ${showName ? 'yes' : 'no'}`,
      '',
      'Confirm your signature:',
      confirmUrl,
      '',
      'Remove your signature, now or any time later:',
      removeUrl,
      '',
      'Signing again with this address sends a new email; a newer email replaces the links in this one.',
      '',
      'If you did not sign, or the details above are wrong, ignore this email and the signature will not be counted.',
      '',
      'Dangerous Robot',
    ].join('\n'),
  };
}

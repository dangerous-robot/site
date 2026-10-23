import type { Env } from './env';

export interface Email {
  to: string;
  subject: string;
  text: string;
  /** Extra message headers; Resend's send API takes them as `headers`. */
  headers?: Record<string, string>;
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
      ...(email.headers ? { headers: email.headers } : {}),
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
  wantsUpdates: boolean;
  confirmUrl: string;
  removeUrl: string;
  /** Set on the reminder: days until an unconfirmed signature is deleted. */
  reminderDaysLeft?: number;
}

export function confirmationEmail({ to, title, name, showName, wantsUpdates, confirmUrl, removeUrl, reminderDaysLeft }: ConfirmationDetails): Email {
  return {
    to,
    subject: reminderDaysLeft === undefined ? `Confirm your signature: ${title}` : `Reminder: confirm your signature: ${title}`,
    text: [
      `Someone, hopefully you, signed "${title}" on dangerousrobot.org with this email address.`,
      ...(reminderDaysLeft !== undefined
        ? [`The signature is not confirmed yet. If it is not confirmed within ${reminderDaysLeft} days, it will be deleted. These links replace the ones in the earlier email.`]
        : []),
      '',
      `Name: ${name}`,
      `Shown on the public list: ${showName ? 'yes' : 'no'}`,
      `Email updates about this campaign: ${wantsUpdates ? 'yes' : 'no'}`,
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

// Replies to messages sent to sign@. RFC 3834: marked as automatic so the sender's own
// auto-responder does not answer back.
const AUTO_REPLY = { 'Auto-Submitted': 'auto-replied' };
const QUESTIONS = 'Questions: contact@dangerousrobot.org.';

export interface ReceiptDetails {
  to: string;
  title: string;
  name: string;
  showName: boolean;
  wantsUpdates: boolean;
  removeUrl: string;
}

export function receiptEmail({ to, title, name, showName, wantsUpdates, removeUrl }: ReceiptDetails): Email {
  return {
    to,
    subject: `Your signature is counted: ${title}`,
    headers: AUTO_REPLY,
    text: [
      `Your signature on "${title}" is counted.`,
      '',
      `Name: ${name}`,
      `Shown on the public list: ${showName ? 'yes' : 'no'}`,
      `Email updates about this campaign: ${wantsUpdates ? 'yes' : 'no'}`,
      '',
      'To remove it, use this link:',
      removeUrl,
      '',
      QUESTIONS,
      '',
      'Dangerous Robot',
    ].join('\n'),
  };
}

/** A reply that counts no signature: unknown petition, closed petition, or no name. */
export function notSignedEmail(to: string, subject: string, why: string): Email {
  return {
    to,
    subject,
    headers: AUTO_REPLY,
    text: [why, '', 'We have not counted a signature.', '', QUESTIONS, '', 'Dangerous Robot'].join('\n'),
  };
}

// Worker-served pages for the no-JS sign result and the email links.
// Inline styles only: these pages load nothing from outside api.dangerousrobot.org.
// Colors and fonts mirror src/styles/tokens.css.

const STYLE = `
:root { color-scheme: dark light; --bg:#19191b; --text:#dcdde0; --heading:#d0d7c7; --accent:#42958b; }
@media (prefers-color-scheme: light) { :root { --bg:#f8f7f4; --text:#18181c; --heading:#18181c; --accent:#287870; } }
body { margin:0; background:var(--bg); color:var(--text); font:1rem/1.6 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
main { max-width:36rem; margin:0 auto; padding:3rem 1rem; }
h1 { font:normal 1.6rem/1.3 Georgia,"Times New Roman",Times,serif; color:var(--heading); margin:0 0 1rem; }
p { margin:0 0 1rem; }
a { color:var(--accent); }
button { font:inherit; padding:.5rem 1.25rem; border:1px solid var(--accent); border-radius:6px; background:var(--accent); color:#fff; cursor:pointer; }
button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
`;

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}

function page(title: string, bodyHtml: string, status = 200): Response {
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>${escapeHtml(title)} · Dangerous Robot</title><style>${STYLE}</style></head>
<body><main>${bodyHtml}</main></body></html>`;
  return new Response(html, {
    status,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      // Email links carry tokens; never leak them to the post via Referer.
      'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
    },
  });
}

function backLink(postUrl: string): string {
  return `<p><a href="${escapeHtml(postUrl)}#sign">Back to the petition</a></p>`;
}

/** One-button landing page: GET never changes data, because email link scanners fetch every URL. */
export function actionPage(heading: string, text: string, action: string, token: string, button: string, postUrl: string): Response {
  return page(heading, `<h1>${escapeHtml(heading)}</h1>
<p>${escapeHtml(text)}</p>
<form method="post" action="${escapeHtml(action)}"><input type="hidden" name="t" value="${escapeHtml(token)}"><button type="submit">${escapeHtml(button)}</button></form>
${backLink(postUrl)}`);
}

export function messagePage(heading: string, text: string, postUrl: string | null, status = 200): Response {
  return page(heading, `<h1>${escapeHtml(heading)}</h1><p>${escapeHtml(text)}</p>${postUrl ? backLink(postUrl) : ''}`, status);
}

// Cloudflare Worker for the public site's page routes (D-035). When the origin cannot answer (the updater closes the
// tunnel during an update, or the VM is down), Cloudflare would show its own branded error page; this Worker shows
// the site's maintenance page instead and passes every other response through unchanged, 404 included.
// Route it on medical.<domain>/* and route medical.<domain>/api/* to no Worker, so questions never pass through it
// (hosting/oracle/README.md). It logs nothing; keep the Worker's observability logs off.

// Cloudflare's codes for an unreachable origin (530 is error 1033, no tunnel connected), plus cloudflared's 502 and
// 504 when the tunnel is up but the page server is not. The page server itself never returns these.
const DOWN = new Set([502, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530]);

// The 404 page's look (frontend/public/error.css), inline because the origin is unreachable when this shows.
export const PAGE = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="30">
<title>Back in a minute · Mr. Healthcare</title>
<style>
:root{--bg:#f4f6f9;--surface:#fff;--text:#0f1b2d;--muted:#536175;--line:#dde3eb;--accent:#0b6e6e;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0c131d;--surface:#131c28;--text:#e6ecf3;--muted:#9aa8b9;--line:#263345;--accent:#3fb8af;color-scheme:dark}}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;box-sizing:border-box;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.card{max-width:28rem;padding:32px;border:1px solid var(--line);border-radius:14px;background:var(--surface);text-align:center}
.mark{margin:0;color:var(--accent);font-size:2.5rem;font-weight:700}
h1{margin:4px 0 8px;font-size:1.4rem}
p{color:var(--muted)}
</style>
</head>
<body>
<main class="card">
<p class="mark" aria-hidden="true">+</p>
<h1>Mr. Healthcare is being updated</h1>
<p>It is usually back within a minute. This page reloads itself every 30 seconds.</p>
</main>
</body>
</html>
`;

const HEADERS = {
  "Content-Type": "text/html; charset=utf-8",
  "Cache-Control": "no-store",
  "Retry-After": "30",
  "X-Robots-Tag": "noindex",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
};

export default {
  async fetch(request) {
    let response = null;
    try {
      // A Worker's fetch to its own zone goes to the origin, not back through this Worker.
      response = await fetch(request);
    } catch {
      // No response at all counts as unreachable.
    }
    if (response && !DOWN.has(response.status)) return response;
    return new Response(request.method === "HEAD" ? null : PAGE, { status: 503, headers: HEADERS });
  },
};

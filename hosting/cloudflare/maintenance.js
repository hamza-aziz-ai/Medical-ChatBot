// Cloudflare Worker for the public site's page routes (D-035). When the origin cannot answer (the updater closes the
// tunnel during an update, or the VM is down), Cloudflare would show its own branded error page; this Worker shows
// the site's maintenance page instead and passes every other response through unchanged, 404 included.
// Route it on medical.<domain>/* and route medical.<domain>/api/* to no Worker, so questions never pass through it
// (hosting/oracle/README.md). It logs nothing; keep the Worker's observability logs off.

// Cloudflare's codes for an unreachable origin (530 is error 1033, no tunnel connected), plus cloudflared's 502 and
// 504 when the tunnel is up but the page server is not. The page server itself never returns these.
const DOWN = new Set([502, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530]);

// An exact copy of frontend/public/error.css below its comment (the test compares them), inline because the origin
// is unreachable when this page shows.
export const STYLE = `:root {
  --bg: #f4f6f9;
  --surface: #ffffff;
  --text: #0f1b2d;
  --muted: #536175;
  --line: #dde3eb;
  --accent: #0b6e6e;
  --accent-hover: #095959;
  --accent-soft: #e3f2f1;
  --on-accent: #ffffff;
  --warn-bg: #fff4e5;
  --warn-text: #7a4100;
  --warn-line: #f2c48d;
  --shadow: 0 1px 2px rgb(15 27 45 / 6%), 0 4px 16px rgb(15 27 45 / 6%);
  --radius: 14px;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color-scheme: light;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0c131d;
    --surface: #131c28;
    --text: #e6ecf3;
    --muted: #9aa8b9;
    --line: #263345;
    --accent: #3fb8af;
    --accent-hover: #5cc8c0;
    --accent-soft: #15322f;
    --on-accent: #06221f;
    --warn-bg: #2d2214;
    --warn-text: #f3c98b;
    --warn-line: #5c4320;
    --shadow: 0 1px 2px rgb(0 0 0 / 30%), 0 6px 20px rgb(0 0 0 / 25%);
    color-scheme: dark;
  }
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.55 var(--font);
  -webkit-font-smoothing: antialiased;
}

.topbar {
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}

.topbar-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  padding: 14px max(20px, env(safe-area-inset-right)) 14px max(20px, env(safe-area-inset-left));
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  color: inherit;
  text-decoration: none;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 11px;
  background: var(--accent);
  color: var(--on-accent);
}

.brand-name {
  display: block;
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.01em;
}

.tagline {
  display: block;
  margin: 0;
  font-size: 0.85rem;
  color: var(--muted);
}

.badge {
  margin: 0;
  padding: 5px 12px;
  border: 1px solid var(--warn-line);
  border-radius: 999px;
  background: var(--warn-bg);
  color: var(--warn-text);
  font-size: 0.8rem;
  font-weight: 600;
  white-space: nowrap;
}

.status {
  flex: 1;
  display: grid;
  place-items: center;
  padding: 32px 16px;
}

.card {
  width: 100%;
  max-width: 30rem;
  padding: 36px 32px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
  text-align: center;
}

.card-mark {
  display: grid;
  place-items: center;
  width: 72px;
  height: 72px;
  margin: 0 auto 18px;
  border-radius: 20px;
  background: var(--accent-soft);
  color: var(--accent);
}

.card-mark.pulse {
  animation: pulse 1.8s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    transform: scale(1.08);
    opacity: 0.7;
  }
}

.card .eyebrow {
  margin: 0 0 6px;
  color: var(--accent);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.card h1 {
  margin: 0 0 10px;
  font-size: 1.5rem;
  line-height: 1.25;
}

.card p {
  margin: 0 0 8px;
  color: var(--muted);
}

.card .hint {
  font-size: 0.85rem;
}

.button {
  display: inline-block;
  margin-top: 12px;
  padding: 10px 20px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
  text-decoration: none;
}

.button:hover {
  background: var(--accent-hover);
}

:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 3px;
}

@media (max-width: 560px) {
  .tagline {
    display: none;
  }

  .card {
    padding: 28px 20px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .card-mark.pulse {
    animation: none;
  }
}
`;

const CROSS = '<path d="M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z" fill="currentColor"/>';

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
${STYLE}</style>
</head>
<body>
<header class="topbar">
<div class="topbar-inner">
<div class="brand">
<span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22">${CROSS}</svg></span>
<span>
<span class="brand-name">Mr. Healthcare</span>
<span class="tagline">Answers from a medical knowledge graph</span>
</span>
</div>
<p class="badge" role="note">Not medical advice</p>
</div>
</header>
<main class="status">
<div class="card" role="status">
<span class="card-mark pulse" aria-hidden="true"><svg viewBox="0 0 24 24" width="34" height="34">${CROSS}</svg></span>
<p class="eyebrow">Updating</p>
<h1>We'll be right back</h1>
<p>Mr. Healthcare is installing an update. It usually takes about a minute.</p>
<p class="hint">This page checks again every 30 seconds.</p>
</div>
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

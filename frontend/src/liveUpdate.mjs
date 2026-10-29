// Keeps an open page current (D-037): it notices the maintenance page while an update has the site closed, and
// reloads itself into a new release, carrying the conversation across the reload in this tab's sessionStorage.

// hosting/cloudflare/maintenance.js answers 503 while the origin is down; the rest are Cloudflare's and
// cloudflared's own codes for an unreachable origin, in case the Worker fails open.
export const DOWN = new Set([502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530]);
export const PROBE_TIMEOUT_MS = 5000;
export const CHECK_EVERY_MS = 30000;
export const CHECK_DOWN_EVERY_MS = 5000;
export const SNAPSHOT_KEY = "mr-healthcare-handoff";
export const MARKER_KEY = "mr-healthcare-reloaded-for";
const SNAPSHOT_VERSION = 1;

// Replaced in tests; jsdom-like environments cannot navigate.
export const page = { reload: () => window.location.reload() };

const ASSET = /\/assets\/[\w.-]+\.(?:js|css)/g;

// The hashed files a page loads, as one comparable string. A release changes at least one of them. Empty when the
// page was not built (the Vite dev server), which turns live updates off.
export function assetKey(text) {
  return [...new Set(text.match(ASSET) || [])].sort().join(" ");
}

export function loadedAssets(doc = document) {
  const urls = [...doc.querySelectorAll("script[src], link[href]")].map((el) => el.getAttribute("src") || el.getAttribute("href"));
  return assetKey(urls.join(" "));
}

// One check of the page itself. state: "down" (maintenance), "same", "new" (key is the new release) or "ignore"
// (offline, timed out, or not the app's page, such as a challenge page); "ignore" must change nothing.
export async function probe(fetchImpl, current, controller = new AbortController()) {
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const response = await fetchImpl("/", { cache: "no-store", signal: controller.signal });
    if (DOWN.has(response.status)) return { state: "down" };
    if (response.status !== 200 || !(response.headers.get("content-type") || "").includes("text/html")) return { state: "ignore" };
    const html = await response.text();
    const key = assetKey(html);
    if (!html.includes('id="app"') || !key) return { state: "ignore" };
    return key === current ? { state: "same" } : { state: "new", key };
  } catch {
    return { state: "ignore" };
  } finally {
    clearTimeout(timer);
  }
}

// Called right before an automatic reload. The marker is written every time, so a stale cache that keeps serving
// the old page cannot cause a second reload for the same release. False means do not reload: already tried for
// this release, or storage is blocked or full (the conversation then stays in page memory).
export function prepareReload(key, snapshot, store = () => globalThis.sessionStorage) {
  try {
    const storage = store();
    if (storage.getItem(MARKER_KEY) === key) return false;
    storage.setItem(MARKER_KEY, key);
    if (snapshot) storage.setItem(SNAPSHOT_KEY, JSON.stringify({ v: SNAPSHOT_VERSION, ...snapshot }));
    return true;
  } catch {
    clearSnapshot(store);
    return false;
  }
}

function validTopic(topic) {
  return topic === null || (typeof topic === "object" && typeof topic.name === "string" && typeof topic.type === "string");
}

// Reads the hand-off once and deletes it at once; anything malformed is dropped.
export function takeSnapshot(store = () => globalThis.sessionStorage) {
  try {
    const storage = store();
    const raw = storage.getItem(SNAPSHOT_KEY);
    storage.removeItem(SNAPSHOT_KEY);
    const snapshot = raw && JSON.parse(raw);
    if (
      snapshot && snapshot.v === SNAPSHOT_VERSION && typeof snapshot.draft === "string" && validTopic(snapshot.topic)
      && Array.isArray(snapshot.messages) && snapshot.messages.length
      && snapshot.messages.every((message) => message && typeof message.agent === "string" && typeof message.type === "string")
    ) {
      return snapshot;
    }
  } catch {
    // Blocked storage or bad JSON: start a new conversation.
  }
  return null;
}

export function clearSnapshot(store = () => globalThis.sessionStorage) {
  try {
    store().removeItem(SNAPSHOT_KEY);
  } catch {
    // Nothing to clear.
  }
}

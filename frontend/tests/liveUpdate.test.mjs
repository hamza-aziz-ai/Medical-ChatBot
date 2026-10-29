import assert from "node:assert/strict";
import test from "node:test";

import { assetKey, MARKER_KEY, prepareReload, probe, SNAPSHOT_KEY, takeSnapshot } from "../src/liveUpdate.mjs";

const OLD = '<div id="app"></div><script type="module" crossorigin src="/assets/index-old.js"></script><link rel="stylesheet" href="/assets/index-a.css">';
const CURRENT = assetKey(OLD);

function html(body, status = 200, type = "text/html") {
  return async () => new Response(body, { status, headers: { "content-type": type } });
}

function memory() {
  const items = new Map();
  return {
    items,
    getItem: (key) => (items.has(key) ? items.get(key) : null),
    setItem: (key, value) => items.set(key, String(value)),
    removeItem: (key) => items.delete(key),
  };
}

test("the asset key covers scripts and stylesheets, so a style-only release counts", () => {
  assert.equal(CURRENT, "/assets/index-a.css /assets/index-old.js");
  assert.notEqual(assetKey(OLD.replace("index-a.css", "index-b.css")), CURRENT);
  assert.equal(assetKey('<script type="module" src="/src/main.js"></script>'), "");
});

test("classifies the page: maintenance, same release, new release", async () => {
  for (const status of [502, 503, 504, 522, 530]) {
    assert.deepEqual(await probe(html("Back in a minute", status), CURRENT), { state: "down" });
  }
  assert.deepEqual(await probe(html(OLD), CURRENT), { state: "same" });
  const next = OLD.replace("index-old.js", "index-new.js");
  assert.deepEqual(await probe(html(next), CURRENT), { state: "new", key: assetKey(next) });
});

test("ignores anything that is not the app's page, so nothing changes", async () => {
  const ignored = [
    html(OLD, 404),
    html(OLD, 200, "application/json"),
    html("<html>Just a moment...</html>"),
    async () => {
      throw new TypeError("offline");
    },
  ];
  for (const fetchImpl of ignored) assert.deepEqual(await probe(fetchImpl, CURRENT), { state: "ignore" });
});

test("a probe that hangs is aborted and ignored", async () => {
  const controller = new AbortController();
  const hanging = (url, { signal }) => new Promise((resolve, reject) => signal.addEventListener("abort", () => reject(signal.reason)));
  const pending = probe(hanging, CURRENT, controller);
  controller.abort();
  assert.deepEqual(await pending, { state: "ignore" });
});

test("reloads once per release, with or without a conversation to carry", () => {
  const storage = memory();
  assert.equal(prepareReload("k1", null, () => storage), true);
  assert.equal(storage.items.has(SNAPSHOT_KEY), false);
  assert.equal(storage.getItem(MARKER_KEY), "k1");
  // A stale cache serving the old page again must not loop.
  assert.equal(prepareReload("k1", null, () => storage), false);
  assert.equal(prepareReload("k2", { messages: [], topic: null, draft: "" }, () => storage), true);
});

test("storage that refuses means no reload and no half-written hand-off", () => {
  const blocked = () => {
    throw new DOMException("denied", "SecurityError");
  };
  assert.equal(prepareReload("k1", null, blocked), false);

  const full = memory();
  full.setItem = (key, value) => {
    if (key === SNAPSHOT_KEY) throw new DOMException("full", "QuotaExceededError");
    full.items.set(key, value);
  };
  assert.equal(prepareReload("k1", { messages: [], topic: null, draft: "x" }, () => full), false);
  assert.equal(full.items.has(SNAPSHOT_KEY), false);
});

test("the hand-off is read once, validated and deleted", () => {
  const storage = memory();
  const snapshot = { messages: [{ agent: "user", type: "text", text: "what causes asthma?" }], topic: { name: "asthma", type: "disease" }, draft: "and" };
  prepareReload("k1", snapshot, () => storage);
  assert.deepEqual(takeSnapshot(() => storage), { v: 1, ...snapshot });
  assert.equal(storage.items.has(SNAPSHOT_KEY), false);
  assert.equal(takeSnapshot(() => storage), null);

  for (const bad of ["{", JSON.stringify({ v: 2, ...snapshot }), JSON.stringify({ ...snapshot, v: 1, messages: [{}] }), JSON.stringify({ v: 1, ...snapshot, topic: "asthma" })]) {
    storage.setItem(SNAPSHOT_KEY, bad);
    assert.equal(takeSnapshot(() => storage), null);
    assert.equal(storage.items.has(SNAPSHOT_KEY), false);
  }
});

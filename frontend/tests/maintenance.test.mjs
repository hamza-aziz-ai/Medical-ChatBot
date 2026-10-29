import assert from "node:assert/strict";
import test from "node:test";

import worker, { PAGE } from "../../hosting/cloudflare/maintenance.js";

async function visit(origin, method = "GET") {
  globalThis.fetch = origin;
  return worker.fetch(new Request("https://example.test/", { method }));
}

test("passes the origin's answers through unchanged, a 404 included", async () => {
  for (const status of [200, 404, 503]) {
    const response = await visit(async () => new Response("origin", { status }));
    assert.equal(response.status, status);
    assert.equal(await response.text(), "origin");
  }
});

test("shows the maintenance page, uncached, when the origin is unreachable", async () => {
  const unreachable = [530, 502, 504, 522].map((status) => async () => new Response("cloudflare", { status }));
  unreachable.push(async () => {
    throw new TypeError("network");
  });
  for (const origin of unreachable) {
    const response = await visit(origin);
    assert.equal(response.status, 503);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    assert.equal(await response.text(), PAGE);
  }
  const head = await visit(async () => new Response(null, { status: 530 }), "HEAD");
  assert.equal(head.status, 503);
});

test("the maintenance page names no vendor or model", () => {
  assert.doesNotMatch(PAGE, /cloudflare|oracle|ollama|gpt|neo4j|docker/i);
});

import assert from "node:assert/strict";
import { test } from "node:test";

import { ERROR_MESSAGE, REQUEST_TIMEOUT_MS, sendMessage } from "../src/chatApi.mjs";

function newState() {
  return { messages: [], botTyping: false, apiToken: "secret" };
}

test("sends the question as a parameter with the token and a timeout", async () => {
  const state = newState();
  let call;
  const http = { get: async (url, options) => { call = { url, options }; return { data: { message: "answer" } }; } };

  await sendMessage(state, http, "http://localhost:5000/", { text: "A+ & B#?" });

  assert.equal(call.url, "http://localhost:5000/");
  assert.deepEqual(call.options.params, { search: "A+ & B#?" });
  assert.equal(call.options.headers.Authorization, "Bearer secret");
  assert.equal(call.options.timeout, REQUEST_TIMEOUT_MS);
  assert.deepEqual(state.messages.map((m) => m.text), ["A+ & B#?", "answer"]);
  assert.equal(state.botTyping, false);
});

test("a failed request shows an error and re-enables input", async () => {
  const state = newState();
  const http = { get: async () => { throw new Error("timeout of 10000ms exceeded"); } };

  await sendMessage(state, http, "http://localhost:5000", { text: "hi" });

  assert.equal(state.messages.at(-1).text, ERROR_MESSAGE);
  assert.equal(state.botTyping, false);
});

test("API errors are shown, and a rejected token is explained", async () => {
  const state = newState();
  const reject = (status, data) => ({ get: async () => { throw { response: { status, data } }; } });

  await sendMessage(state, reject(400, { error: "Questions are limited to 500 characters." }), "x", { text: "q" });
  assert.equal(state.messages.at(-1).text, "Questions are limited to 500 characters.");

  await sendMessage(state, reject(401, { error: "Missing or invalid API token." }), "x", { text: "q" });
  assert.match(state.messages.at(-1).text, /token was rejected/);
  assert.equal(state.botTyping, false);
});

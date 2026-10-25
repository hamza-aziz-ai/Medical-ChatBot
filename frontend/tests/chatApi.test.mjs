import assert from "node:assert/strict";
import { test } from "node:test";

import { ERROR_MESSAGE, REQUEST_TIMEOUT_MS, createFetchHttp, sendMessage } from "../src/chatApi.mjs";

function newState() {
  return { messages: [], botTyping: false };
}

test("sends the question as a parameter with a timeout and no credentials", async () => {
  const state = newState();
  let call;
  const http = { get: async (url, options) => { call = { url, options }; return { data: { message: "answer" } }; } };

  await sendMessage(state, http, "http://localhost:5000/", { text: "A+ & B#?" });

  assert.equal(call.url, "http://localhost:5000/");
  assert.deepEqual(call.options.params, [["search", "A+ & B#?"]]);
  assert.equal(call.options.headers, undefined);
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

test("API errors are shown, and rate limiting is explained", async () => {
  const state = newState();
  const reject = (status, data) => ({ get: async () => { throw { response: { status, data } }; } });

  await sendMessage(state, reject(400, { error: "Questions are limited to 500 characters." }), "x", { text: "q" });
  assert.equal(state.messages.at(-1).text, "Questions are limited to 500 characters.");

  await sendMessage(state, reject(429, null), "x", { text: "q" });
  assert.match(state.messages.at(-1).text, /Too many questions/);
  assert.equal(state.botTyping, false);
});

function respond(status, body, { invalidJson = false } = {}) {
  return async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (invalidJson) throw new SyntaxError("Unexpected token");
      return body;
    },
  });
}

const options = { params: { search: "A+ & B#?" }, timeout: 1000 };

test("fetch adapter encodes parameters and returns the reply", async () => {
  let seen;
  const http = createFetchHttp(async (url, init) => { seen = { url, init }; return respond(200, { message: "ok" })(); });
  const res = await http.get("http://localhost:5000/", options);
  assert.equal(res.data.message, "ok");
  assert.equal(seen.url, "http://localhost:5000/?search=A%2B+%26+B%23%3F");
  assert.equal(seen.init.headers, undefined);
  assert.ok(seen.init.signal instanceof AbortSignal);
});

test("fetch adapter turns HTTP errors into { response: { status, data } }", async () => {
  for (const status of [400, 429, 503]) {
    const http = createFetchHttp(respond(status, { error: `status ${status}` }));
    await assert.rejects(http.get("x", options), (error) => error.response.status === status && error.response.data.error === `status ${status}`);
  }
});

test("fetch adapter rejects malformed successful replies", async () => {
  await assert.rejects(createFetchHttp(respond(200, null, { invalidJson: true })).get("x", options), /Malformed/);
  await assert.rejects(createFetchHttp(respond(200, { other: 1 })).get("x", options), /Malformed/);
});

test("fetch adapter aborts slow requests and the UI recovers", async () => {
  const hanging = (url, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
  const http = createFetchHttp(hanging);
  await assert.rejects(http.get("x", { ...options, timeout: 20 }), { name: "AbortError" });

  const state = { messages: [], botTyping: false };
  await sendMessage(state, { get: (url, opts) => http.get(url, { ...opts, timeout: 20 }) }, "x", { text: "hi" });
  assert.equal(state.messages.at(-1).text, ERROR_MESSAGE);
  assert.equal(state.botTyping, false);
});

test("network failures show the controlled error", async () => {
  const state = { messages: [], botTyping: false };
  await sendMessage(state, createFetchHttp(async () => { throw new TypeError("Failed to fetch"); }), "x", { text: "hi" });
  assert.equal(state.messages.at(-1).text, ERROR_MESSAGE);
  assert.equal(state.botTyping, false);
});

test("sends the confirmed topic and clarification choices, and keeps the structured reply", async () => {
  const state = { messages: [], botTyping: false, topic: { name: "asthma", type: "disease" }, conversation: 1 };
  let call;
  const reply = { status: "answer", message: "m", answers: [{ intent: "disease_cause" }], options: [{ label: "x" }],
    topic: { name: "anemia", type: "disease" }, interpretation: { used_topic: false } };
  const http = { get: async (url, options) => { call = options; return { data: reply }; } };

  await sendMessage(state, http, "x", { text: "q", label: "anemia as a disease", selections: [{ name: "anemia", type: "disease" }] });

  assert.deepEqual(call.params, [["search", "q"], ["topic", "asthma"], ["topic_type", "disease"], ["selection", "anemia:disease"]]);
  assert.equal(state.messages[0].text, "anemia as a disease");
  const bot = state.messages.at(-1);
  assert.equal(bot.type, "answer");
  assert.deepEqual(bot.options, [{ label: "x" }]);
  assert.deepEqual(state.topic, { name: "anemia", type: "disease" });
});

test("an answer about several subjects clears the topic; an abstention keeps it", async () => {
  const state = { messages: [], botTyping: false, topic: { name: "asthma", type: "disease" }, conversation: 1 };
  const answer = (data) => ({ get: async () => ({ data }) });
  await sendMessage(state, answer({ status: "abstain", message: "no", topic: null }), "x", { text: "q" });
  assert.deepEqual(state.topic, { name: "asthma", type: "disease" });
  await sendMessage(state, answer({ status: "answer", message: "two", topic: null }), "x", { text: "q" });
  assert.equal(state.topic, null);
});

test("a reply that arrives after a new conversation started is dropped", async () => {
  const state = { messages: [], botTyping: false, topic: null, conversation: 1 };
  let finish;
  const http = { get: () => new Promise((resolve) => { finish = resolve; }) };
  const pending = sendMessage(state, http, "x", { text: "q" });
  state.conversation = 2;
  state.messages = [];
  finish({ data: { status: "answer", message: "late", topic: { name: "asthma", type: "disease" } } });
  await pending;
  assert.deepEqual(state.messages, []);
  assert.equal(state.topic, null);
});


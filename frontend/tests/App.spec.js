import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App.vue";
import { MARKER_KEY, page, SNAPSHOT_KEY } from "@/liveUpdate.mjs";

function reply(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

async function ask(wrapper, question) {
  await wrapper.find("textarea").setValue(question);
  await wrapper.find("textarea").trigger("keydown", { key: "Enter" });
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("App", () => {
  it("sends the question through the real transport, with no credentials, and shows the reply", async () => {
    const fetch = vi.fn(async () => reply(200, { message: "The possible causes of asthma are: dust" }));
    vi.stubGlobal("fetch", fetch);
    const wrapper = mount(App);

    await ask(wrapper, "what causes asthma?");
    await flushPromises();

    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("http://localhost:5000/?search=what+causes+asthma%3F");
    expect(init.headers).toBeUndefined();
    expect(wrapper.find('[role="log"]').text()).toContain("The possible causes of asthma are: dust");
  });

  it("sends only one request while a reply is pending", async () => {
    let finish;
    const fetch = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetch);
    const wrapper = mount(App);

    await ask(wrapper, "first");
    await wrapper.find("textarea").setValue("second");
    await wrapper.find("textarea").trigger("keydown", { key: "Enter" });
    await wrapper.find("form").trigger("submit");
    await wrapper.vm.messageSendHandler("direct");
    expect(fetch).toHaveBeenCalledTimes(1);

    finish(reply(200, { message: "done" }));
    await flushPromises();
    expect(wrapper.find('button[type="submit"]').element.disabled).toBe(false);
  });

  it("shows API errors and lets the user try again", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(reply(429, null))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetch);
    const wrapper = mount(App);

    await ask(wrapper, "q1");
    await flushPromises();
    expect(wrapper.text()).toContain("Too many questions");
    expect(wrapper.find(".message.is-error").exists()).toBe(true);

    await ask(wrapper, "q2");
    await flushPromises();
    expect(wrapper.text()).toContain("couldn't get an answer");
    expect(wrapper.find("textarea").element.disabled).toBe(false);
  });

  it("notes external AI processing in the About card only, naming no vendor", () => {
    const wrapper = mount(App);
    expect(wrapper.find(".about").text()).toContain("Questions are processed on this site's servers and may pass through external hosting, network and AI services");
    expect(wrapper.text()).not.toMatch(/ollama|gpt-oss/i);
  });

  it("shows the medical-advice notice and makes no external image requests", () => {
    const wrapper = mount(App);
    expect(wrapper.find('[role="note"]').text()).toContain("Not medical advice");
    expect(wrapper.text()).toContain("Always consult a qualified medical professional.");
    expect(wrapper.findAll("img").filter((img) => /^https?:/.test(img.attributes("src") || ""))).toHaveLength(0);
  });

  it("links to the source repository in a new tab without an opener", () => {
    const link = mount(App).find(".repo-link");
    expect(link.attributes("href")).toBe("https://github.com/hamza-aziz-ai/Medical-ChatBot");
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
    expect(link.attributes("aria-label")).toBeTruthy();
  });

  it("sends the confirmed topic with a follow-up and forgets it on a new conversation", async () => {
    const fetch = vi.fn(async () => reply(200, { status: "answer", message: "m", answers: [], options: [],
      topic: { name: "asthma", type: "disease" }, interpretation: null }));
    vi.stubGlobal("fetch", fetch);
    const wrapper = mount(App);

    await ask(wrapper, "what causes asthma?");
    await flushPromises();
    await ask(wrapper, "and prevention?");
    await flushPromises();
    expect(fetch.mock.calls[1][0]).toContain("topic=asthma&topic_type=disease");

    await wrapper.find("button.ghost").trigger("click");
    expect(wrapper.find(".topic").exists()).toBe(false);
    await ask(wrapper, "and prevention?");
    await flushPromises();
    expect(fetch.mock.calls[2][0]).not.toContain("topic=");
  });

  describe("live updates (D-037)", () => {
    const OLD = '<div id="app"></div><script type="module" src="/assets/index-old.js"></script>';
    const NEW = OLD.replace("index-old", "index-new");
    let script;
    let wrapper;

    function pageReply(status, body = "") {
      return { ok: status === 200, status, headers: new Headers({ "content-type": "text/html" }), text: async () => body };
    }

    // The page probe goes to "/", questions to the API; each gets its own fake.
    function stubFetch(pageResponse, apiFetch = async () => reply(200, { status: "answer", message: "m", answers: [] })) {
      const fetch = vi.fn(async (url, init) => (url === "/" ? pageResponse() : apiFetch(url, init)));
      vi.stubGlobal("fetch", fetch);
      return fetch;
    }

    beforeEach(() => {
      // A built page loads hashed assets; without them live updates stay off, as on the dev server. A link without
      // rel stands in for the entry script, which the test DOM would try to load.
      script = document.createElement("link");
      script.setAttribute("href", "/assets/index-old.js");
      document.head.append(script);
      vi.spyOn(page, "reload").mockImplementation(() => {});
    });

    afterEach(() => {
      wrapper.unmount();
      script.remove();
      vi.restoreAllMocks();
    });

    it("restores the conversation, topic and draft carried across a reload, and deletes the hand-off", async () => {
      sessionStorage.setItem(SNAPSHOT_KEY, JSON.stringify({
        v: 1,
        messages: [{ agent: "user", type: "text", text: "what causes asthma?" }, { agent: "bot", type: "answer", text: "Dust.", answers: [], options: [] }],
        topic: { name: "asthma", type: "disease" },
        draft: "and prevention",
      }));
      stubFetch(() => pageReply(200, OLD));
      wrapper = mount(App);
      await flushPromises();

      expect(wrapper.text()).toContain("what causes asthma?");
      expect(wrapper.find(".topic").text()).toContain("asthma");
      expect(wrapper.find("textarea").element.value).toBe("and prevention");
      expect(sessionStorage.getItem(SNAPSHOT_KEY)).toBeNull();
    });

    it("shows maintenance without losing the conversation, blocks every send path, and lifts it when the site is back", async () => {
      let status = 503;
      const fetch = stubFetch(() => (status === 503 ? pageReply(503, "Back in a minute") : pageReply(200, OLD)));
      wrapper = mount(App);
      await wrapper.find("textarea").setValue("what causes asthma?");
      await wrapper.vm.check();
      await flushPromises();

      expect(wrapper.find(".maintenance").exists()).toBe(true);
      expect(wrapper.find(".typing").exists()).toBe(false);
      expect(wrapper.find("button.send").attributes("disabled")).toBeDefined();
      expect(wrapper.findAll("button.chip").every((chip) => chip.attributes("disabled") !== undefined)).toBe(true);
      await wrapper.find("textarea").trigger("keydown", { key: "Enter" });
      await wrapper.vm.messageSendHandler({ text: "what causes asthma?" });
      expect(fetch.mock.calls.filter(([url]) => url !== "/")).toHaveLength(0);

      status = 200;
      await wrapper.vm.check();
      await flushPromises();
      expect(wrapper.find(".maintenance").exists()).toBe(false);
      expect(wrapper.find("textarea").element.value).toBe("what causes asthma?");
      expect(page.reload).not.toHaveBeenCalled();
    });

    it("waits for a pending reply before reloading into a new release, then carries the whole conversation", async () => {
      let answer;
      stubFetch(() => pageReply(200, NEW), () => new Promise((resolve) => {
        answer = () => resolve(reply(200, { status: "answer", message: "Dust.", answers: [], topic: { name: "asthma", type: "disease" } }));
      }));
      wrapper = mount(App);
      await ask(wrapper, "what causes asthma?");
      await wrapper.vm.check();
      await flushPromises();
      expect(page.reload).not.toHaveBeenCalled();

      answer();
      await flushPromises();
      expect(page.reload).toHaveBeenCalledTimes(1);
      const snapshot = JSON.parse(sessionStorage.getItem(SNAPSHOT_KEY));
      expect(snapshot.messages.map((message) => message.text)).toEqual([expect.any(String), "what causes asthma?", "Dust."]);
      expect(snapshot.topic).toEqual({ name: "asthma", type: "disease" });
    });

    it("waits for IME composition to end and keeps the composed text", async () => {
      stubFetch(() => pageReply(200, NEW));
      wrapper = mount(App);
      const textarea = wrapper.find("textarea");
      await textarea.trigger("compositionstart");
      await wrapper.vm.check();
      await flushPromises();
      expect(page.reload).not.toHaveBeenCalled();

      textarea.element.value = "喘息";
      await textarea.trigger("compositionend");
      await flushPromises();
      expect(page.reload).toHaveBeenCalledTimes(1);
      expect(JSON.parse(sessionStorage.getItem(SNAPSHOT_KEY)).draft).toBe("喘息");
    });

    it("reloads an empty conversation without storing it, and only once per release even if the old page comes back", async () => {
      stubFetch(() => pageReply(200, NEW));
      wrapper = mount(App);
      await wrapper.vm.check();
      await wrapper.vm.check();
      await flushPromises();

      expect(page.reload).toHaveBeenCalledTimes(1);
      expect(sessionStorage.getItem(SNAPSHOT_KEY)).toBeNull();
      expect(sessionStorage.getItem(MARKER_KEY)).toBe("/assets/index-new.js");
    });
  });
});

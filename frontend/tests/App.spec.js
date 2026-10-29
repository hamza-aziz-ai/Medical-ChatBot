import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "@/App.vue";

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
});


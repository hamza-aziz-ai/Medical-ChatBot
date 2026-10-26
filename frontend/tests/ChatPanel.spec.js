import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ChatPanel from "@/components/ChatPanel.vue";

function panel(props = {}) {
  return mount(ChatPanel, { props: { messages: [], ...props } });
}

describe("ChatPanel", () => {
  it("is ready to use without any credentials", () => {
    const wrapper = panel();
    expect(wrapper.find("textarea").element.disabled).toBe(false);
    expect(wrapper.find('input[type="password"]').exists()).toBe(false);
  });

  it("labels every control", () => {
    const wrapper = panel();
    for (const id of ["question"]) {
      expect(wrapper.find(`label[for="${id}"]`).exists()).toBe(true);
    }
    expect(wrapper.find('[role="log"]').attributes("aria-live")).toBe("polite");
  });

  it("sends with Enter and with the button, trimmed", async () => {
    const wrapper = panel();
    const box = wrapper.find("textarea");
    await box.setValue("  symptoms of asthma  ");
    await box.trigger("keydown", { key: "Enter" });
    await box.setValue("causes of asthma");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([[{ text: "symptoms of asthma" }], [{ text: "causes of asthma" }]]);
    expect(box.element.value).toBe("");
  });

  it("does not send on Shift+Enter, during IME composition, or when empty", async () => {
    const wrapper = panel();
    const box = wrapper.find("textarea");
    await box.setValue("first line");
    await box.trigger("keydown", { key: "Enter", shiftKey: true });
    await box.trigger("keydown", { key: "Enter", isComposing: true });
    await box.setValue("   ");
    await box.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("send")).toBeUndefined();
  });

  it("limits questions to the API's 500 characters", () => {
    expect(panel().find("textarea").attributes("maxlength")).toBe("500");
  });

  it("blocks keyboard and button submits while a reply is pending", async () => {
    const wrapper = panel({ busy: true });
    const box = wrapper.find("textarea");
    await box.setValue("anything");
    await box.trigger("keydown", { key: "Enter" });
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
    expect(wrapper.find('button[type="submit"]').element.disabled).toBe(true);
    expect(wrapper.text()).toContain("Looking that up");
  });

  it("offers example questions until the user asks one", async () => {
    const suggestions = ["What causes migraine?", "How can I prevent anemia?"];
    const wrapper = panel({ suggestions, messages: [{ agent: "bot", text: "Hello" }] });
    const chips = wrapper.findAll(".chip");
    expect(chips.map((c) => c.text())).toEqual(suggestions);
    await chips[0].trigger("click");
    expect(wrapper.emitted("send")[0][0]).toMatchObject({ text: "What causes migraine?", label: "What causes migraine?" });
    await wrapper.setProps({ messages: [{ agent: "bot", text: "Hello" }, { agent: "user", text: "q" }] });
    expect(wrapper.find(".chip").exists()).toBe(false);
  });

  it("does not send an example question while a reply is pending", async () => {
    const wrapper = panel({ busy: true, suggestions: ["What causes migraine?"], messages: [] });
    await wrapper.find(".chip").trigger("click");
    expect(wrapper.emitted("send")).toBeUndefined();
  });

  it("shows how many characters are used", async () => {
    const wrapper = panel();
    await wrapper.find("textarea").setValue("abc");
    expect(wrapper.find(".count").text()).toBe("3/500");
  });

  it("renders message text literally, with speaker labels", () => {
    const wrapper = panel({
      messages: [
        { agent: "user", text: "<b>bold?</b>" },
        { agent: "bot", text: "line one\nline two" },
      ],
    });
    expect(wrapper.find("b").exists()).toBe(false);
    expect(wrapper.text()).toContain("<b>bold?</b>");
    expect(wrapper.findAll(".speaker").map((s) => s.text())).toEqual(["You", "Mr. Healthcare"]);
  });

  it("renders list answers as bullets with their note", () => {
    const wrapper = panel({ messages: [{ agent: "bot", type: "answer", text: "t", answers: [
      { intent: "disease_cure_way", subject: "asthma", lead: "Treatments recorded for asthma:", items: ["rest", "inhaler"], note: "This is not medical advice" },
    ] }] });
    expect(wrapper.findAll(".items li").map((li) => li.text())).toEqual(["rest", "inhaler"]);
    expect(wrapper.find(".note").text()).toBe("This is not medical advice.");
  });

  it("renders long answers as headed sections with numbered points", () => {
    const wrapper = panel({ messages: [{ agent: "bot", type: "answer", text: "t", answers: [{ intent: "disease_prevention", subject: "asthma", text: "t",
      lead: "Precautions for asthma include:", sections: [
        { heading: "Daily prevention", paragraph: null, items: ["Avoid allergens.", "No pets indoors."] },
        { heading: null, paragraph: "See a doctor.", items: [] }] }] }] });
    expect(wrapper.find(".section-heading").text()).toBe("Daily prevention");
    expect(wrapper.findAll("ol.items li").map((li) => li.text())).toEqual(["Avoid allergens.", "No pets indoors."]);
    expect(wrapper.text()).toContain("See a doctor.");
  });

  it("offers the latest reply's options and sends their question, choices and topic", async () => {
    const options = [
      { label: "anemia as a disease", question: "q", selections: [{ name: "anemia", type: "disease" }] },
      { label: "anemia as a symptom", question: "q", selections: [{ name: "anemia", type: "symptom" }] },
    ];
    const wrapper = panel({ messages: [{ agent: "user", text: "q" }, { agent: "bot", type: "clarify", text: "Which?", options }] });
    expect(wrapper.find(".suggestions").attributes("aria-label")).toBe("Choose what you meant");
    await wrapper.findAll(".chip")[0].trigger("click");
    expect(wrapper.emitted("send")[0][0]).toEqual({ text: "q", label: "anemia as a disease", selections: options[0].selections, topic: undefined });
  });

  it("explains how a question was understood", () => {
    const wrapper = panel({ messages: [{ agent: "bot", type: "answer", text: "t", answers: [],
      interpretation: { entities: [{ name: "asthma", types: ["disease"] }], intents: [{ intent: "disease_cause", label: "Causes" }], used_topic: true,
        aliases: [{ alias: "whooping cough", name: "pertussis" }] } }] });
    const why = wrapper.find(".why").text();
    expect(why).toContain("asthma (disease)");
    expect(why).toContain("Causes");
    expect(why).toContain("referred back");
    expect(why).toContain('"whooping cough" was read as pertussis');
  });

  it("says when a language model helped read the question, naming no vendor", () => {
    const interpretation = { entities: [], intents: [], used_topic: false, aliases: [] };
    const read = panel({ messages: [{ agent: "bot", type: "answer", text: "t", answers: [], interpretation: { ...interpretation, understood_by: "model" } }] });
    expect(read.find(".why").text()).toContain("A language model helped read your question");
    expect(read.text()).not.toMatch(/ollama|gpt-oss/i);
    const rules = panel({ messages: [{ agent: "bot", type: "answer", text: "t", answers: [], interpretation }] });
    expect(rules.find(".why").text()).not.toContain("language model");
  });

  it("links one-disease answers to MedlinePlus as an external site", () => {
    const wrapper = panel({ messages: [{ agent: "bot", type: "answer", text: "t",
      answers: [{ intent: "disease_cause", subject: "asthma", text: "The possible causes of asthma are: dust" }] }] });
    const link = wrapper.find("a.external");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
    expect(link.attributes("href")).toContain("query=asthma");
    expect(link.text()).toContain("external site");
  });

  it("shows the current topic and asks the page to reset", async () => {
    const wrapper = panel({ topic: { name: "asthma", type: "disease" } });
    expect(wrapper.find(".topic").text()).toContain("asthma");
    await wrapper.find("button.ghost").trigger("click");
    expect(wrapper.emitted("reset")).toHaveLength(1);
  });
});

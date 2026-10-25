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
    expect(wrapper.emitted("send")).toEqual([["symptoms of asthma"], ["causes of asthma"]]);
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
    expect(wrapper.find("button").element.disabled).toBe(true);
    expect(wrapper.text()).toContain("Looking that up");
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
});

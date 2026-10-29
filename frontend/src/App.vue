<template>
  <div class="app">
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <span
            class="brand-mark"
            aria-hidden="true"
          >
            <svg
              viewBox="0 0 24 24"
              width="22"
              height="22"
            ><path
              d="M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z"
              fill="currentColor"
            /></svg>
          </span>
          <div>
            <h1>Mr. Healthcare</h1>
            <p class="tagline">
              Answers from a medical knowledge graph
            </p>
          </div>
        </div>
        <div class="topbar-actions">
          <p
            class="badge"
            role="note"
          >
            Not medical advice
          </p>
          <a
            class="repo-link"
            href="https://github.com/hamza-aziz-ai/Medical-ChatBot"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Source code on GitHub (external site)"
            title="Source code on GitHub"
          >
            <svg
              viewBox="0 0 16 16"
              width="22"
              height="22"
              aria-hidden="true"
            ><path
              d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
              fill="currentColor"
            /></svg>
          </a>
        </div>
      </div>
    </header>

    <p
      class="emergency"
      role="note"
    >
      If this may be an emergency, call your local emergency number now. This chatbot cannot help in an emergency.
    </p>

    <div
      v-if="down"
      class="maintenance"
    >
      <div
        class="maintenance-card"
        role="status"
      >
        <p class="eyebrow">
          Updating
        </p>
        <h2>We'll be right back</h2>
        <p>Mr. Healthcare is installing an update. It usually takes about a minute.</p>
        <p class="hint">
          Your conversation is kept. This page continues by itself.
        </p>
      </div>
    </div>

    <main class="workspace">
      <ChatPanel
        ref="chat"
        :messages="messages"
        :busy="botTyping"
        :paused="down"
        :suggestions="suggestions"
        :topic="topic"
        @send="messageSendHandler"
        @reset="newConversation"
        @composed="$nextTick(reloadWhenIdle)"
      />
      <MedicalChatbot />
    </main>

    <footer class="footer">
      <p>
        Answers come from a dataset whose source and clinical accuracy are unverified. Always consult a qualified medical professional.
      </p>
      <p>B.Tech final-year project by Hamza Aziz and Mahak Agrawal.</p>
    </footer>
  </div>
</template>

<script>
import ChatPanel from "@/components/ChatPanel.vue";
import MedicalChatbot from "@/components/MedicalChatbot.vue";
import { fetchHttp, sendMessage } from "@/chatApi.mjs";
import {
  CHECK_DOWN_EVERY_MS, CHECK_EVERY_MS, clearSnapshot, loadedAssets, page, prepareReload, probe, takeSnapshot,
} from "@/liveUpdate.mjs";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";

function welcome() {
  return {
    agent: "bot",
    type: "text",
    text: "Hello! I'm Mr. Healthcare. Ask me about the symptoms, causes, prevention, treatments or complications of a disease. You can ask follow-ups such as \"what causes it?\".",
  };
}

export default {
  name: "App",
  components: { ChatPanel, MedicalChatbot },
  data() {
    return {
      messages: [welcome()],
      botTyping: false,
      // The confirmed subject for follow-ups ("what causes it?"). Held in page memory; stored only to carry it across
      // an automatic reload into a new release (D-037).
      topic: null,
      // True while the site answers with the maintenance page (D-037); sending is blocked, the conversation kept.
      down: false,
      // The asset key of a newer release, waiting for the page to be idle before reloading into it.
      release: null,
      // Bumped by "New conversation" so a late reply from the old conversation is dropped.
      conversation: 0,
      // Each one is answered by the shipped graph (see eval/cases.jsonl).
      suggestions: [
        "What are the symptoms of asthma?",
        "What causes migraine?",
        "How can I prevent anemia?",
        "Which diseases cause tiredness?",
      ],
    };
  },
  watch: {
    botTyping(typing) {
      if (!typing) this.reloadWhenIdle();
    },
  },
  created() {
    const snapshot = takeSnapshot();
    if (snapshot) {
      this.messages = snapshot.messages;
      this.topic = snapshot.topic;
    }
    this.restoredDraft = snapshot ? snapshot.draft : "";
  },
  mounted() {
    if (this.restoredDraft) this.$refs.chat.draft = this.restoredDraft;
    // Only a built page loads hashed assets; the dev server has none, so live updates stay off there.
    this.assets = loadedAssets();
    if (!this.assets) return;
    this.onVisible = () => {
      if (document.visibilityState === "visible") this.check();
    };
    document.addEventListener("visibilitychange", this.onVisible);
    this.schedule();
  },
  unmounted() {
    this.gone = true;
    clearTimeout(this.timer);
    if (this.controller) this.controller.abort();
    if (this.onVisible) document.removeEventListener("visibilitychange", this.onVisible);
  },
  methods: {
    async messageSendHandler(value) {
      if (this.botTyping || this.down) return;
      await sendMessage(this, fetchHttp, API_BASE_URL, typeof value === "string" ? { text: value } : value);
      // A failed question may mean the site just closed for an update: look now rather than at the next check.
      const last = this.messages[this.messages.length - 1];
      if (last && last.type === "error") this.check();
    },
    newConversation() {
      this.conversation += 1;
      this.messages = [welcome()];
      this.topic = null;
      this.botTyping = false;
      clearSnapshot();
    },
    schedule() {
      clearTimeout(this.timer);
      if (!this.gone) this.timer = setTimeout(() => this.check(), this.down ? CHECK_DOWN_EVERY_MS : CHECK_EVERY_MS);
    },
    // One check at a time, only while the page is visible; becoming visible again starts the next one.
    async check() {
      if (!this.assets || this.checking || this.gone) return;
      if (document.visibilityState === "hidden") {
        clearTimeout(this.timer);
        return;
      }
      this.checking = true;
      this.controller = new AbortController();
      try {
        const result = await probe((...args) => globalThis.fetch(...args), this.assets, this.controller);
        if (result.state === "down") this.down = true;
        else if (result.state === "same") this.down = false;
        else if (result.state === "new") {
          this.down = false;
          this.release = result.key;
          this.reloadWhenIdle();
        }
      } finally {
        this.checking = false;
        this.schedule();
      }
    },
    // Never while a reply is pending or text is being composed (IME), so nothing typed or asked is lost.
    reloadWhenIdle() {
      const chat = this.$refs.chat;
      if (!this.release || this.botTyping || !chat || chat.composing) return;
      const asked = this.messages.some((message) => message.agent === "user");
      const snapshot = asked || this.topic || chat.draft.trim()
        ? { messages: this.messages, topic: this.topic, draft: chat.draft }
        : null;
      const key = this.release;
      this.release = null;
      if (prepareReload(key, snapshot)) page.reload();
    },
  },
};
</script>

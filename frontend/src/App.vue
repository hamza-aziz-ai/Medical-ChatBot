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

    <main class="workspace">
      <ChatPanel
        :messages="messages"
        :busy="botTyping"
        :suggestions="suggestions"
        :topic="topic"
        @send="messageSendHandler"
        @reset="newConversation"
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
      // The confirmed subject for follow-ups ("what causes it?"). Held in page memory only, never stored.
      topic: null,
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
  methods: {
    messageSendHandler(value) {
      if (this.botTyping) return Promise.resolve();
      return sendMessage(this, fetchHttp, API_BASE_URL, typeof value === "string" ? { text: value } : value);
    },
    newConversation() {
      this.conversation += 1;
      this.messages = [welcome()];
      this.topic = null;
      this.botTyping = false;
    },
  },
};
</script>

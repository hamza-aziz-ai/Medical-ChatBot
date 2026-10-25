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
        <p
          class="badge"
          role="note"
        >
          Not medical advice
        </p>
      </div>
    </header>

    <main class="workspace">
      <ChatPanel
        :messages="messages"
        :busy="botTyping"
        :suggestions="suggestions"
        @send="messageSendHandler"
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

export default {
  name: "App",
  components: { ChatPanel, MedicalChatbot },
  data() {
    return {
      messages: [
        {
          agent: "bot",
          type: "text",
          text: "Hello! I'm Mr. Healthcare. Ask me about the symptoms, causes, prevention, treatments or complications of a disease.",
        },
      ],
      botTyping: false,
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
    messageSendHandler(text) {
      if (this.botTyping) return Promise.resolve();
      return sendMessage(this, fetchHttp, API_BASE_URL, { text });
    },
  },
};
</script>

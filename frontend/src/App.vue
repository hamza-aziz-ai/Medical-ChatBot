<template>
  <div class="layout">
    <header class="site-header">
      <h1>Mr. Healthcare</h1>
      <p class="subtitle">
        B.Tech final-year project by Hamza Aziz and Mahak Agrawal
      </p>
      <p
        class="notice"
        role="note"
      >
        <strong>Not medical advice.</strong> Answers come from a dataset whose source and clinical accuracy are unverified.
        Always consult a qualified medical professional.
      </p>
    </header>

    <main class="workspace">
      <ChatPanel
        :messages="messages"
        :busy="botTyping"
        @send="messageSendHandler"
      />
      <MedicalChatbot />
    </main>
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
          text: "Hello! I'm Mr. Healthcare. Ask me about the symptoms, causes, prevention or treatments of a disease.",
        },
      ],
      botTyping: false,
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

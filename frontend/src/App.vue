<template>
  <div id="app">
    <MedicalChatbot />
    <label class="api-token" for="api-token">
      API token
      <input id="api-token" v-model="apiToken" type="password" autocomplete="off" />
    </label>
    <VueBotUI
        :messages="messages"
        :options="botOptions"
        :bot-typing="botTyping"
        :input-disable="botTyping || !apiToken"
        @msg-send="messageSendHandler"
    />
  </div>
</template>

<script>
import axios from "axios";
import {VueBotUI} from "vue-bot-ui";
import MedicalChatbot from "@/components/MedicalChatbot.vue";
import { sendMessage } from "@/chatApi.mjs";

const API_BASE_URL = process.env.VUE_APP_API_BASE_URL || "http://localhost:5000";

export default {
  name: 'App',
  components: {
    MedicalChatbot,
    VueBotUI,
  },
  data() {
    return {
      messages: [],
      botTyping: false,
      // Held in memory only: never stored or compiled into the bundle.
      apiToken: "",
      botOptions: {
        botTitle: "Mr. Healthcare",
        botAvatarImg: "https://www.shareicon.net/data/512x512/2016/07/05/791221_man_512x512.png",
        msgBubbleBgUser: "#892cdc",
        boardContentBg: "#151515",
        colorScheme: "#892cdc",
      },
    };
  },
  mounted() {
    this.messages.push({
      agent: "bot",
      type: "text",
      text: "Hello! I'm Mr. Healthcare. How can I help you?",
    });
  },
  methods: {
    messageSendHandler(value) {
      return sendMessage(this, axios, API_BASE_URL, value);
    },
  },
};
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
#app {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
}
.api-token {
  position: fixed;
  top: 16px;
  right: 16px;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  background: #151515;
  color: #fff;
  font-size: 13px;
}
</style>

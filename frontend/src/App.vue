<template>
  <div id="app">
    <MedicalChatbot />
    <VueBotUI
        :messages="messages"
        :options="botOptions"
        :bot-typing="botTyping"
        :input-disable="botTyping"
        @msg-send="messageSendHandler"
    />
  </div>
</template>

<script>
import axios from "axios";
import {VueBotUI} from "vue-bot-ui";
import MedicalChatbot from "@/components/MedicalChatbot.vue";

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
      this.messages.push({
        agent: "user",
        type: "text",
        text: value.text,
      });

      this.botTyping = true;

      axios.get("http://localhost:5000/?search="+value.text).then((res) => {
        console.log(res);

        this.messages.push({
          agent: "bot",
          type: "text",
          text: res.data.message,
        });

        this.botTyping = false;
      });
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
</style>

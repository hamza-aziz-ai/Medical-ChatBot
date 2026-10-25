<template>
  <section
    class="chat-panel"
    aria-labelledby="chat-title"
  >
    <h2 id="chat-title">
      Ask a question
    </h2>

    <div class="field">
      <label for="api-token">API token</label>
      <input
        id="api-token"
        type="password"
        autocomplete="off"
        :value="token"
        aria-describedby="token-help"
        @input="$emit('update:token', $event.target.value)"
      >
      <p
        id="token-help"
        class="hint"
      >
        The value of CHATBOT_API_TOKEN. This page keeps it in memory only and never saves it.
      </p>
    </div>

    <ol
      ref="transcript"
      class="transcript"
      role="log"
      aria-live="polite"
      aria-label="Conversation"
    >
      <li
        v-for="(message, index) in messages"
        :key="index"
        :class="['message', message.agent === 'user' ? 'from-user' : 'from-bot']"
      >
        <span class="speaker">{{ message.agent === "user" ? "You" : "Mr. Healthcare" }}</span>
        <p class="text">
          {{ message.text }}
        </p>
      </li>
      <li
        v-if="busy"
        class="message from-bot typing"
      >
        <span class="speaker">Mr. Healthcare</span>
        <p class="text">
          Looking that up…
        </p>
      </li>
    </ol>

    <form
      class="composer"
      @submit.prevent="submit"
    >
      <label for="question">Your question</label>
      <div class="composer-row">
        <textarea
          id="question"
          v-model="draft"
          rows="2"
          :maxlength="maxLength"
          :disabled="!token"
          :aria-describedby="token ? 'question-help' : 'token-needed'"
          placeholder="For example: what are the symptoms of asthma?"
          @keydown.enter="onEnter"
        />
        <button
          type="submit"
          :disabled="!canSend"
        >
          Send
        </button>
      </div>
      <p
        v-if="!token"
        id="token-needed"
        class="hint"
      >
        Enter the API token to start.
      </p>
      <p
        v-else
        id="question-help"
        class="hint"
      >
        Enter sends; Shift+Enter adds a new line. Up to {{ maxLength }} characters.
      </p>
    </form>
  </section>
</template>

<script>
export default {
  name: "ChatPanel",
  props: {
    messages: { type: Array, required: true },
    busy: { type: Boolean, default: false },
    token: { type: String, default: "" },
    maxLength: { type: Number, default: 500 },
  },
  emits: ["send", "update:token"],
  data() {
    return { draft: "" };
  },
  computed: {
    canSend() {
      return Boolean(this.token) && !this.busy && this.draft.trim().length > 0;
    },
  },
  watch: {
    "messages.length"() {
      this.$nextTick(() => {
        const list = this.$refs.transcript;
        if (list) list.scrollTop = list.scrollHeight;
      });
    },
  },
  methods: {
    onEnter(event) {
      // Shift+Enter adds a line; Enter during IME composition confirms the composition.
      if (event.shiftKey || event.isComposing || event.keyCode === 229) return;
      event.preventDefault();
      this.submit();
    },
    submit() {
      // The guard lives here so keyboard and button submissions are both protected.
      if (!this.canSend) return;
      this.$emit("send", this.draft.trim());
      this.draft = "";
    },
  },
};
</script>

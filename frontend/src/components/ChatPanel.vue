<template>
  <section
    class="chat-panel"
    aria-labelledby="chat-title"
  >
    <div class="panel-header">
      <h2 id="chat-title">
        Conversation
      </h2>
      <p class="panel-hint">
        Symptoms, causes, prevention, treatments and complications of about 650 diseases
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
        :class="['message', message.agent === 'user' ? 'from-user' : 'from-bot', { 'is-error': message.type === 'error' }]"
      >
        <span
          v-if="message.agent !== 'user'"
          class="avatar"
          aria-hidden="true"
        >MH</span>
        <div class="bubble">
          <span class="speaker">{{ message.agent === "user" ? "You" : "Mr. Healthcare" }}</span>
          <p class="text">
            {{ message.text }}
          </p>
        </div>
      </li>
      <li
        v-if="busy"
        class="message from-bot typing"
      >
        <span
          class="avatar"
          aria-hidden="true"
        >MH</span>
        <div class="bubble">
          <span class="speaker">Mr. Healthcare</span>
          <p class="text">
            <span class="visually-hidden">Looking that up…</span>
            <span
              class="dots"
              aria-hidden="true"
            ><i /><i /><i /></span>
          </p>
        </div>
      </li>
    </ol>

    <div
      v-if="showSuggestions"
      class="suggestions"
      aria-label="Example questions"
      role="group"
    >
      <button
        v-for="suggestion in suggestions"
        :key="suggestion"
        type="button"
        class="chip"
        :disabled="busy"
        @click="ask(suggestion)"
      >
        {{ suggestion }}
      </button>
    </div>

    <form
      class="composer"
      @submit.prevent="submit"
    >
      <label
        for="question"
        class="visually-hidden"
      >Your question</label>
      <div class="composer-box">
        <textarea
          id="question"
          v-model="draft"
          rows="1"
          :maxlength="maxLength"
          aria-describedby="question-help"
          placeholder="Ask about a disease or symptom…"
          @keydown.enter="onEnter"
        />
        <button
          type="submit"
          class="send"
          :disabled="!canSend"
          aria-label="Send"
        >
          <svg
            viewBox="0 0 24 24"
            width="20"
            height="20"
            aria-hidden="true"
          ><path
            d="M3 20.5 21 12 3 3.5 3 10l12 2-12 2z"
            fill="currentColor"
          /></svg>
        </button>
      </div>
      <p
        id="question-help"
        class="hint"
      >
        <span>Enter to send · Shift+Enter for a new line</span>
        <span class="count">{{ draft.length }}/{{ maxLength }}</span>
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
    suggestions: { type: Array, default: () => [] },
    maxLength: { type: Number, default: 500 },
  },
  emits: ["send"],
  data() {
    return { draft: "" };
  },
  computed: {
    canSend() {
      return !this.busy && this.draft.trim().length > 0;
    },
    // Examples help until the user has asked something of their own.
    showSuggestions() {
      return this.suggestions.length > 0 && !this.messages.some((message) => message.agent === "user");
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
    ask(question) {
      if (this.busy) return;
      this.$emit("send", question);
    },
  },
};
</script>

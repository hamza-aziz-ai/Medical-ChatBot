<template>
  <section
    class="chat-panel"
    aria-labelledby="chat-title"
  >
    <div class="panel-header">
      <div>
        <h2 id="chat-title">
          Conversation
        </h2>
        <p class="panel-hint">
          Symptoms, causes, prevention, treatments and complications of about 650 diseases
        </p>
      </div>
      <button
        type="button"
        class="ghost"
        @click="$emit('reset')"
      >
        New conversation
      </button>
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
        :class="['message', message.agent === 'user' ? 'from-user' : 'from-bot', { 'is-error': message.type === 'error', 'is-abstain': message.type === 'abstain' }]"
      >
        <span
          v-if="message.agent !== 'user'"
          class="avatar"
          aria-hidden="true"
        >MH</span>
        <div class="bubble">
          <span class="speaker">{{ message.agent === "user" ? "You" : "Mr. Healthcare" }}</span>
          <template v-if="message.answers && message.answers.length">
            <div
              v-for="(answer, answerIndex) in message.answers"
              :key="answerIndex"
              class="answer"
            >
              <template v-if="answer.items">
                <p class="text">
                  {{ answer.lead }}
                </p>
                <ul class="items">
                  <li
                    v-for="item in answer.items"
                    :key="item"
                  >
                    {{ item }}
                  </li>
                </ul>
                <p
                  v-if="answer.note"
                  class="note"
                >
                  {{ answer.note }}.
                </p>
              </template>
              <template v-else-if="answer.sections">
                <p class="text">
                  {{ answer.lead }}
                </p>
                <div
                  v-for="(section, sectionIndex) in answer.sections"
                  :key="sectionIndex"
                  class="section"
                >
                  <p
                    v-if="section.heading"
                    class="section-heading"
                  >
                    {{ section.heading }}
                  </p>
                  <p
                    v-if="section.paragraph"
                    class="text"
                  >
                    {{ section.paragraph }}
                  </p>
                  <ol
                    v-if="section.items.length"
                    class="items"
                  >
                    <li
                      v-for="(item, itemIndex) in section.items"
                      :key="itemIndex"
                    >
                      {{ item }}
                    </li>
                  </ol>
                </div>
              </template>
              <p
                v-else
                class="text"
              >
                {{ answer.text }}
              </p>
            </div>
          </template>
          <p
            v-else
            class="text"
          >
            {{ message.text }}
          </p>

          <details
            v-if="message.interpretation"
            class="why"
          >
            <summary>Why this answer?</summary>
            <ul>
              <li v-if="message.interpretation.entities.length">
                Understood topic: {{ describeEntities(message.interpretation.entities) }}
              </li>
              <li v-if="message.interpretation.intents.length">
                Question type: {{ message.interpretation.intents.map((item) => item.label).join(", ") }}
              </li>
              <li
                v-for="alias in message.interpretation.aliases || []"
                :key="alias.alias"
              >
                "{{ alias.alias }}" was read as {{ alias.name }}, another name for it.
              </li>
              <li v-if="message.interpretation.used_topic">
                Your question referred back to the previous topic.
              </li>
              <li v-if="message.interpretation.understood_by === 'model'">
                A language model helped read your question. The facts still come only from the knowledge graph.
              </li>
              <li>Facts come from an unverified dataset in the knowledge graph. This is not medical advice.</li>
            </ul>
          </details>

          <a
            v-if="learnMore(message)"
            class="external"
            :href="learnMore(message).url"
            target="_blank"
            rel="noopener noreferrer"
          >Learn more about {{ learnMore(message).name }} on MedlinePlus (external site)</a>
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
      v-if="chips.length"
      class="suggestions"
      :aria-label="chipsLabel"
      role="group"
    >
      <button
        v-for="chip in chips"
        :key="chip.label"
        type="button"
        class="chip"
        :disabled="busy"
        @click="ask(chip)"
      >
        {{ chip.label }}
      </button>
    </div>

    <form
      class="composer"
      @submit.prevent="submit"
    >
      <p
        v-if="topic"
        class="topic"
      >
        Talking about <strong>{{ topic.name }}</strong> ({{ topic.type }}). Follow-ups such as "what causes it?" use this topic.
      </p>
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
const MEDLINEPLUS_SEARCH = "https://vsearch.nlm.nih.gov/vivisimo/cgi-bin/query-meta?v%3Aproject=medlineplus&v%3Asources=medlineplus-bundle&query=";

export default {
  name: "ChatPanel",
  props: {
    messages: { type: Array, required: true },
    busy: { type: Boolean, default: false },
    suggestions: { type: Array, default: () => [] },
    topic: { type: Object, default: null },
    maxLength: { type: Number, default: 500 },
  },
  emits: ["send", "reset"],
  data() {
    return { draft: "" };
  },
  computed: {
    canSend() {
      return !this.busy && this.draft.trim().length > 0;
    },
    lastBotMessage() {
      const last = this.messages[this.messages.length - 1];
      return last && last.agent === "bot" ? last : null;
    },
    // Chips belong to the latest reply only: examples before the first question, then that reply's options.
    chips() {
      if (!this.messages.some((message) => message.agent === "user")) {
        return this.suggestions.map((question) => ({ label: question, question }));
      }
      return (this.lastBotMessage && this.lastBotMessage.options) || [];
    },
    chipsLabel() {
      return this.lastBotMessage && this.lastBotMessage.type === "clarify" ? "Choose what you meant" : "Suggested questions";
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
      this.$emit("send", { text: this.draft.trim() });
      this.draft = "";
    },
    ask(chip) {
      if (this.busy) return;
      this.$emit("send", { text: chip.question, label: chip.label, selections: chip.selections, topic: chip.topic });
    },
    describeEntities(entities) {
      return entities.map((entity) => `${entity.name} (${entity.types.join(" or ")})`).join(", ");
    },
    // Only for an answer about one disease; the link is outside information, not a source for the answer.
    learnMore(message) {
      const answers = message.answers || [];
      const subjects = new Set(answers.filter((answer) => answer.intent.startsWith("disease_")).map((answer) => answer.subject));
      if (message.type !== "answer" || subjects.size !== 1) return null;
      const [name] = subjects;
      return { name, url: MEDLINEPLUS_SEARCH + encodeURIComponent(name) };
    },
  },
};
</script>

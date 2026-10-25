export const REQUEST_TIMEOUT_MS = 10000;
export const ERROR_MESSAGE = "Sorry, I couldn't get an answer right now. Please try again.";

function errorText(error) {
  const response = error && error.response;
  if (response && response.status === 429) {
    return "Too many questions at once. Please wait a moment and try again.";
  }
  return (response && response.data && response.data.error) || ERROR_MESSAGE;
}

// Minimal GET client with the axios-like contract sendMessage expects:
// resolves to { data } on success and throws { response: { status, data } } on HTTP errors.
export function createFetchHttp(fetchImpl = (...args) => globalThis.fetch(...args)) {
  return {
    async get(url, { params, timeout }) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      try {
        const response = await fetchImpl(`${url}?${new URLSearchParams(params)}`, { signal: controller.signal });
        let data;
        try {
          data = await response.json();
        } catch {
          data = null;
        }
        if (!response.ok) {
          throw { response: { status: response.status, data: data || {} } };
        }
        if (!data || typeof data.message !== "string") {
          throw new Error("Malformed response from the API");
        }
        return { data };
      } finally {
        clearTimeout(timer);
      }
    },
  };
}

export const fetchHttp = createFetchHttp();

// value: { text, label?, selections?, topic? }. text is what is asked; label is what the user's bubble shows
// (a chip may show "anemia as a disease" while re-asking the original question with that choice).
export async function sendMessage(state, http, baseUrl, value) {
  const conversation = state.conversation;
  state.messages.push({ agent: "user", type: "text", text: value.label || value.text });
  state.botTyping = true;

  // Repeatable parameters, so they are sent as pairs. The topic and choices are held in page memory only.
  const params = [["search", value.text]];
  const topic = value.topic === undefined ? state.topic : value.topic;
  if (topic) params.push(["topic", topic.name], ["topic_type", topic.type]);
  for (const choice of value.selections || []) params.push(["selection", `${choice.name}:${choice.type}`]);

  let reply;
  try {
    const res = await http.get(baseUrl.replace(/\/+$/, "") + "/", { params, timeout: REQUEST_TIMEOUT_MS });
    reply = res.data;
  } catch (error) {
    reply = { status: "error", message: errorText(error) };
  }
  // A reply that arrives after "New conversation" belongs to the old conversation: drop it.
  if (state.conversation !== conversation) return;
  state.botTyping = false;

  state.messages.push({
    agent: "bot",
    // type "error" lets the page style failures differently from answers.
    type: reply.status || "text",
    text: reply.message,
    answers: reply.answers || [],
    options: reply.options || [],
    interpretation: reply.interpretation || null,
  });
  if (reply.topic) state.topic = reply.topic;
  else if (reply.status === "answer") state.topic = null;
}

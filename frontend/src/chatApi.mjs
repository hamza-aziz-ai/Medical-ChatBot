export const REQUEST_TIMEOUT_MS = 10000;
export const ERROR_MESSAGE = "Sorry, I couldn't get an answer right now. Please try again.";

function errorText(error) {
  const response = error && error.response;
  if (response && response.status === 401) {
    return "The API token was rejected. Check it and try again.";
  }
  return (response && response.data && response.data.error) || ERROR_MESSAGE;
}

export async function sendMessage(state, http, baseUrl, value) {
  state.messages.push({ agent: "user", type: "text", text: value.text });
  state.botTyping = true;

  try {
    const res = await http.get(baseUrl.replace(/\/+$/, "") + "/", {
      params: { search: value.text },
      headers: { Authorization: `Bearer ${state.apiToken}` },
      timeout: REQUEST_TIMEOUT_MS,
    });
    state.messages.push({ agent: "bot", type: "text", text: res.data.message });
  } catch (error) {
    state.messages.push({ agent: "bot", type: "text", text: errorText(error) });
  } finally {
    state.botTyping = false;
  }
}

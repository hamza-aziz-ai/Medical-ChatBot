# FEATURE-003: Professional UI redesign

**Goal.** A cleaner, more professional page (owner's request), without new dependencies or external requests (D-014).

**Scope.** `frontend/src/App.vue`, `components/ChatPanel.vue`, `components/MedicalChatbot.vue`, `assets/style.css`, `chatApi.mjs` (error messages carry `type: "error"`), and the component tests.

**Design.** A top bar with a brand mark and a "Not medical advice" badge; a full-height conversation card with avatars, a typing indicator, red-tinted error replies, a send button and a character counter; example questions (all answered by the shipped graph) shown until the user asks one, as a single scrolling row on phones; an About card with graph counts and collapsible "What you can ask", "How it works" and "Limits"; a footer with the disclaimer and credits. Light and dark themes follow the system setting. Every text and background pair meets WCAG AA (lowest 5.26:1).

**Status.** Done on branch `feat/ui-redesign`.

**Open questions.** None.

## Log

- 2026-10-25: Built and checked in a browser against the real stack (answer, example question, abstention) and with `vite preview` at 960 px and 390 px in both themes, with no horizontal overflow. Frontend lint clean; 8 helper and 14 component tests passed.
- 2026-10-27: New favicon (teal speech bubble with a graph-node cross, from an owner-chosen generated image): 16 and 32 px PNGs, a 48 px ICO and a 180 px Apple touch icon, transparent background.

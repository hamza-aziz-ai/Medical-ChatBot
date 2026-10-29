# FEATURE-018: An open page follows updates by itself

**Goal.** A page left open sees the maintenance view while the site is updated and then runs the new release by itself, without losing the conversation (D-037).

**Scope.** `frontend/src/liveUpdate.mjs` (checks, hand-off, loop marker), `frontend/src/App.vue` (timers, maintenance view, deferred reload, restore), `frontend/src/components/ChatPanel.vue` (`paused`, IME `composing`), `frontend/src/assets/style.css`, the About note, `docker/nginx.conf` (`no-cache` for the page), `scripts/compose_smoke.sh` (header checks), `frontend/tests/liveUpdate.test.mjs` and `frontend/tests/App.spec.js`.

**Design.** See D-037.

**Status.** Built 2026-10-30; live with the next release.

**Open questions.** None.

## Log

- 2026-10-30: Built. Lint clean; 30 component tests and 22 helper tests pass; build ok. In Chrome against `vite preview`: renaming the bundle made the open page reload into it within 30 s with its question, error reply and unsent draft, and the hand-off was gone afterwards; a later rebuild did the same again. A stubbed 503 showed the maintenance view (send disabled, no typing indicator) and lifted it within 5 s of the page coming back, conversation and draft intact.
- 2026-10-30: v1.1.25 deployed by hand at 00:53:56 to 00:54:39 IST, with the centred last line and the full page's pulsing cross in the maintenance view.
- 2026-10-30: Live since v1.1.24. With the tunnel stopped for 35 s (00:40:53 to 00:41:33 IST) the owner's open page showed the maintenance view with its conversation kept. Its last line was off-centre: it shared the composer's `.hint` class (a flex row); it now has its own `.maintenance-hint`.
- 2026-10-30: A-26 verified by the owner on the public site: the open page reloaded into v1.1.25 by itself with its conversation, and a final 40 s tunnel stop (01:10:27 to 01:11:07 IST) showed and lifted the maintenance view as expected.

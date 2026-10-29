# FEATURE-017: A link to the source repository

**Goal.** Visitors can open the project's GitHub repository from the top corner of the page.

**Scope.** `frontend/src/App.vue` (the link beside the "Not medical advice" badge), `frontend/src/assets/style.css` (`.topbar-actions`, `.repo-link`) and one test in `frontend/tests/App.spec.js`.

**Design.** An inline SVG of the GitHub mark, coloured with `currentColor` from `--text`: light on the dark theme, dark on the light theme. No external image or script, so the page's `default-src 'self'` policy is unchanged. It opens in a new tab with `rel="noopener noreferrer"`, like the MedlinePlus links, and has an accessible name.

**Status.** Built 2026-10-29; live with the next release.

**Open questions.** None.

## Log

- 2026-10-29: Built. Lint clean, 25 component tests pass, build ok; checked in the dark theme with `vite preview`.

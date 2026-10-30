# FEATURE-021: Search engine basics for the public site

**Goal.** Search engines index the public site under one name, "Mr. Healthcare - The Medical ChatBot", tied to its authors and the portfolio.

**Scope.** `frontend/index.html` (title, `og:title`, `twitter:title`, canonical link, JSON-LD), `frontend/public/robots.txt`, `frontend/public/sitemap.xml`, and three checks in `scripts/compose_smoke.sh`.

**Design.** D-041. A `WebApplication` with the authors Hamza Aziz (url https://hamzaaziz.dev/) and Mahak Agrawal, no `sameAs`. The portfolio card at https://hamzaaziz.dev/#mr-healthcare takes the same name (portfolio session). The resume at https://hamzaaziz.dev/hamza-aziz-cv/ has no entry yet; its session waits for the owner.

**Status.** Built 2026-10-30; live with the next release.

**Open questions.** Whether the resume gets an entry (owner's decision in the resume session).

## Log

- 2026-10-30: Built. Lint clean, 30 component tests and the helper tests pass, build ok; the built page's JSON-LD parses. The smoke checks run in CI.

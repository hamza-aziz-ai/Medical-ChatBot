# FEATURE-021: Search engine basics for the public site

**Goal.** Search engines index the public site under one name, "Mr. Healthcare - The Medical ChatBot", tied to its authors and the portfolio.

**Scope.** `frontend/index.html` (title, `og:title`, `twitter:title`, canonical link, JSON-LD), `frontend/public/robots.txt`, `frontend/public/sitemap.xml`, and three checks in `scripts/compose_smoke.sh`.

**Design.** D-041. A `WebApplication` with the authors Hamza Aziz (url https://hamzaaziz.dev/) and Mahak Agrawal, no `sameAs`. The portfolio card at https://hamzaaziz.dev/#mr-healthcare takes the same name (portfolio session). The resume at https://hamzaaziz.dev/hamza-aziz-cv/ has the same name and links to the site and the repository (resume session, approved by the owner there); its Word versions are unchanged.

**Status.** Live since v1.1.26 (2026-10-30).

**Open questions.** The owner's LinkedIn Projects entry still has an older title and lists "Mahak"; only the owner changes it.

## Log

- 2026-10-30: Built. Lint clean, 30 component tests and the helper tests pass, build ok; the built page's JSON-LD parses. The smoke checks run in CI.
- 2026-10-30: Live. The public site shows the full title and serves the sitemap, and `robots.txt` shows the site's own file; Cloudflare's generated one, served while the origin had none, is gone. The portfolio card and the resume entry were checked on their live pages.

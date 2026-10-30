# Changelog

Every release of Mr. Healthcare, newest first, with the pull requests it contains. Releases are cut automatically by `release.yml` after every gate passes (D-019), and each release's GitHub notes list the same pull requests. A pull request that changes only documentation ships no images, so it is listed under the next release. Dates are in IST.

## Unreleased

- Record v1.1.26's update and the search work on the portfolio and resume (A-27, A-28)

## v1.1.26 (2026-10-30)

- Search engine basics: full name in the titles, canonical link, robots.txt, sitemap and structured data, D-041 ([#88](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/88))
- The hosted updater moves its own checkout to each release it deploys, D-040 ([#87](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/87))
- The updater removes old release images after each update, keeping the current and previous ones, D-039 ([#86](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/86))
- Record the open page's live updates verified on the public site, A-26 ([#85](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/85))
- Add CHANGELOG.md and bring the docs and both artifacts up to date with D-037, D-038 ([#84](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/84))

## v1.1.25 (2026-10-30)

- Maintenance view: centre the last line, add the pulsing cross ([#83](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/83))

## v1.1.24 (2026-10-30)

- Let an open page follow updates and keep its conversation (D-037) ([#82](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/82))

## v1.1.23 (2026-10-29)

- Order the maintenance Worker's setup so no question is ever logged ([#75](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/75))
- Record the maintenance page working at the v1.1.22 update (A-25) ([#76](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/76))
- README: System Diagram, Solution Architecture, and details moved to docs/guides/ ([#77](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/77))
- Detailed Solution Architecture and Software & System Design diagrams; README section renamed to System Design ([#78](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/78))
- Tidy the Solution architecture diagram in ARCHITECTURE.md ([#79](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/79))
- Tidy the Software & System Design diagram in FLOW.md ([#80](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/80))
- Add a GitHub link to the page's top corner ([#81](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/81))

## v1.1.22 (2026-10-29)

- Give the 404 and maintenance pages the site's header and look (D-035) ([#74](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/74))

## v1.1.21 (2026-10-29)

- The site's own 404 and maintenance pages (D-035) ([#73](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/73))

## v1.1.20 (2026-10-28)

- Let a release wait for main's workflow files (BUG-004) ([#71](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/71))
- Serve all ten pilot rewordings the owner approved ([#72](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/72))

## v1.1.19 (2026-10-28)

- Record the model live on the public site ([#69](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/69))
- Serve the two reworded answers the owner approved ([#70](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/70))

## v1.1.18 (2026-10-27)

- Relay the hosted model through a signed-in Ollama on the free plan ([#68](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/68))

## v1.1.17 (2026-10-27)

- Add link-preview tags and image ([#67](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/67))

## v1.1.16 (2026-10-27)

- Switch the language model on for the public site (D-033) ([#66](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/66))

## v1.1.15 (2026-10-27)

- Let the hosted proxy check run in the release job ([#63](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/63))
- Record the public deployment and BUG-004 ([#64](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/64))
- Replace the favicon with the speech-bubble graph icon ([#65](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/65))

## v1.1.14 (2026-10-27)

- Bring the README, architecture map and defense brief up to date ([#57](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/57))
- Mirror release images to Docker Hub (D-030) ([#58](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/58))
- Record the v1.1.13 Docker Hub backfill ([#59](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/59))
- Docker Hub pages from docs/dockerhub, immutable tags, OCI labels (D-031) ([#60](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/60))
- Record the Docker Hub categories ([#61](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/61))
- Public hosting on an Oracle VM with Aura and a Cloudflare Tunnel (D-032); fix BUG-003 ([#62](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/62))

## v1.1.13 (2026-10-26)

- Round 2: the running language-model setup on a fresh set ([#55](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/55))
- Reworded answers, built up to the owner's review (D-029) ([#56](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/56))

## v1.1.12 (2026-10-26)

- Count language-model outcomes and budget denials ([#54](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/54))

## v1.1.11 (2026-10-26)

- Mark every API response no-store (D-029) ([#53](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/53))

## v1.1.10 (2026-10-26)

- Record the manual v1.1.9 deploy in HANDOVER ([#51](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/51))
- Show long answers as sections and numbered points, without changing a word (D-028) ([#52](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/52))

## v1.1.9 (2026-10-26)

- Keep the AI-processing note generic and in the About card only ([#50](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/50))

## v1.1.8 (2026-10-26)

- Dataset pilot step 2: an unreviewed candidate list for the 451 unmatched names ([#41](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/41))
- Record the observed per-address behaviour of the suggestion budget ([#42](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/42))
- Name v1.1.7 as the last known good release ([#43](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/43))
- Pre-register the step-3 language-model experiment (D-026) ([#44](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/44))
- Step 3: the frozen understanding set and the rule baseline ([#45](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/45))
- Keep the frozen understanding set byte-identical on every platform ([#46](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/46))
- Step 3: run the language-model experiment; the bar is not met ([#47](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/47))
- Align the dataset pilot report's tables ([#48](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/48))
- Let the language model read questions at runtime (D-027) ([#49](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/49))

## v1.1.7 (2026-10-26)

- Give each client a spelling-suggestion budget (A-14) ([#40](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/40))

## v1.1.6 (2026-10-26)

- Dataset pilot, step 1: measure name overlap with MedlinePlus and the Disease Ontology ([#36](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/36))
- Update the handover after the overnight work ([#37](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/37))
- Add a rollback drill for the stack updater (and its first passing run) ([#38](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/38))
- Fingerprint each import's plan and refuse questions while the graph doesn't match (D35) ([#39](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/39))

## v1.1.5 (2026-10-26)

- D35: read the dictionary once at start; one recovery for partial imports ([#35](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/35))

## v1.1.4 (2026-10-26)

- Add GET /health: ready only when the graph matches the dictionary ([#34](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/34))

## v1.1.3 (2026-10-26)

- Cap spelling-suggestion work with a 150 ms time budget (A-14) ([#33](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/33))

## v1.1.2 (2026-10-26)

- Fix the scheduled-task command for PowerShell ([#30](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/30))
- Bring the defense brief up to date (D-015 to D-021) ([#31](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/31))
- Suggest whole names that contain filler words or keywords (A-13) ([#32](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/32))

## v1.1.1 (2026-10-25)

- Automatic releases, part 2: one release per merge ([#28](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/28))
- Update the local stack automatically when a release is published ([#29](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/29))

## v1.1.0 (2026-10-25)

- Fix knowledge-graph self-loops and add a permanent integrity check ([#14](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/14))
- Merge pull requests automatically once every check passes ([#15](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/15))
- Adopt the Defend What You Ship field guide with a docs/ set ([#16](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/16))
- Align the Markdown tables in docs/ ([#17](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/17))
- Drop the defense-brief rewrite from the handover ([#18](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/18))
- Share one instruction file and one memory across all coding agents ([#19](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/19))
- Write decision options as numbered lists ([#20](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/20))
- Remove the API token; rate-limit the API in nginx instead ([#21](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/21))
- Redesign the UI with a clinical, self-contained look ([#22](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/22))
- Guided conversation: structured replies, follow-ups, clarification and suggestions ([#23](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/23))
- Understand sourced aliases and offer confirmed typo suggestions ([#24](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/24))
- Correct the recorded cause of the Codex council failure ([#25](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/25))
- Do not read words inside a matched name as intent keywords (BUG-002) ([#26](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/26))
- Automatic releases, part 1: plan, publish after the gates, manual start ([#27](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/27))

## v1.0.0 (2026-10-25)

- Fix the agreed defect register (High, Medium and Low) ([#1](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/1))
- Fix the remaining known issues (D31-D41) where possible ([#8](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/8))
- Load local secrets from .env and quiet importer notifications ([#10](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/10))
- Add rotating per-module file logging ([#11](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/11))
- Migrate the frontend to Vue 3 and Vite with an accessible chat panel ([#12](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/12))
- Add path-filtered CI, a knowledge-graph MLOps pipeline and guarded release delivery ([#13](https://github.com/hamza-aziz-ai/Medical-ChatBot/pull/13))

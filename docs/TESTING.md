# TESTING

What to run before a change counts as done, and what a pass looks like. Paste the real output into the PR or report; never just say "tests pass".

## Commands and expected results

| Check                                   | Command (from the repository root unless noted)                                                                                          | A pass looks like                                                                                                                                                                         |
|-----------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Backend, offline                        | `python -m pytest tests`                                                                                                                 | `198 passed, 9 skipped` (the 9 live tests skip without a server)                                                                                                                          |
| Backend, live                           | Start a disposable Neo4j, set `NEO4J_TEST_URI`, `NEO4J_PASSWORD`, `NEO4J_TEST_ALLOW_WIPE=1`, then `python -m pytest tests`               | `207 passed`, no skips                                                                                                                                                                    |
| Frontend                                | In `frontend/`: `yarn lint`, `yarn test`, `yarn build`                                                                                   | Lint clean; 11 helper and 20 component tests pass; build writes `dist/`                                                                                                                   |
| Graph build and MLOps gate              | With `NEO4J_URI` and `NEO4J_PASSWORD` set: `python api/build_medicalgraph.py` then `python scripts/evaluate_kg.py report.json`           | Import ends "Import committed and entity dictionary published."; the report shows `"passed": true`, 22/22 cases, no count mismatches, no integrity failures and `chip_mismatches` 0       |
| Containers end to end                   | `bash scripts/compose_smoke.sh`                                                                                                          | `Compose smoke test passed`                                                                                                                                                               |
| Workflows (also in CI: `workflows.yml`) | `docker run --rm -v "$PWD:/repo:ro" -w /repo rhysd/actionlint:1.7.12`                                                                    | No output, exit 0                                                                                                                                                                         |

CI runs the matching checks automatically by path (see the README, CI/CD and MLOps) and `automerge.yml` merges only when all of them pass.

## Manual customer path

Start the stack (`docker compose up -d` after the one-time import), open http://127.0.0.1:8080, then ask: "what are the symptoms of asthma" (expect a list including "breathing difficulty"), "how long does asthma last" (expect "I cannot answer...").

## Pre-ship gate (Lane B; run before any release a real user depends on)

- [ ] I can explain how this works at a high level, without notes.
- [ ] `docs/defense/DEFENSE-medical-chatbot.md` is in my own words and current.
- [ ] I know why we chose this approach over at least one alternative.
- [ ] I can name who could abuse it and what stops them.
- [ ] I know the first place it will fail and how I would notice.
- [ ] I know the main data structures and why they fit.
- [ ] I read the full diff, not just the AI's summary.
- [ ] Tests ran and I saw the real output.
- [ ] A customer path was tried by hand end to end.
- [ ] No secrets, keys or tokens landed in the code.
- [ ] New dependencies are justified and logged.
- [ ] Rollback steps are written and the last good commit is known.
- [ ] Unverified assumptions are cleared or consciously accepted.
- [ ] HANDOVER.md and DECISIONS.md are updated.

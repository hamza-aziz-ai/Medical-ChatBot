# THREAT

Who could behave badly, what they could send, see or break, and what stops them. Known gaps are listed honestly.

| Actor and entry point | Worst realistic abuse | Mitigation in place | Known gap |
|---|---|---|---|
| Anonymous caller on the network, `GET /` (API) | Use the API without permission; flood it | Bearer token compared in constant time; dev server binds 127.0.0.1; Docker publishes only the web port, on 127.0.0.1 | No rate limiting; anyone on the machine can try tokens |
| Token holder, `GET /?search=` | Injection through the question; huge inputs | Parameterized Cypher only; read routing; 500-character limit; GET only; 5 s query timeout | One shared token for everyone; no per-user revocation |
| Malicious web page in the same browser | Read the token or call the API cross-site | Exact-origin CORS; token held in page memory only, never stored | A compromised browser extension could read memory |
| Hostile text in data or answers | Script injection in the page | Text-only rendering (no `v-html`); CSP `default-src 'self'` behind nginx | — |
| Anyone reading logs | Learn users' questions or the token | Questions, entities and tokens never logged; nginx access and error logs discarded; gunicorn access log off | Third-party libraries log to `external.log`; reviewed at WARNING level |
| Contributor or collaborator, pull requests | Merge harmful code or data | All checks must pass; automerge only for same-repository branches, never forks or drafts; `--match-head-commit` | No human review by design (D-010): a passing but wrong change merges |
| Bad CSV contributor, `api/data/medical.csv` | Plant false medical facts or break the graph | Field quarantine, conflict exclusion, refusal guards, integrity check, reviewed baseline counts | Plausible but false facts pass every structural check; no clinical review (D30) |
| Compromised dependency or action | Run code in CI or the images | Exact pins, actions by SHA, base images by digest, Dependabot, `yarn audit` | A pinned package could still be malicious upstream |
| Release workflow | Publish an untested or overwritten image | Tag must be on main and stable SemVer; all gates at that SHA; smoke test of exact digests; no overwrites, no `latest` | — |
| Someone with the repository's secrets | Reach the Neo4j database | Secrets only in git-ignored `.env`; CI uses a throwaway password; old password rotated (D11) | `.env` is plain text on the developer machine |

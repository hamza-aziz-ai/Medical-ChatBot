# CONSTRAINTS

Hard rules for anyone, human or AI, changing this repository. If a change would break one, stop and ask the owner first.

## Lane

Lane A today: a local student prototype with no real users. The owner asked for the guide to be followed anyway, so documentation is kept at Lane B standard. The moment anyone outside the owner relies on it, it is Lane B and the pre-ship gate in [TESTING.md](TESTING.md) applies to every release.

## Never

- Never read, print, copy or commit the contents of `.env`, real passwords or tokens. Real secrets live only in the git-ignored `.env`; `.env.example` holds names and safe defaults only.
- Never log a question, an entity name taken from a question, a token or a credential. Log lengths, counts, intent names and exception types only.
- Never put the API token in a `VITE_*` variable or a Docker build argument; Vite compiles those into the public bundle.
- Never render answer or question text as HTML (`v-html`) in the frontend.
- Never paste values into Cypher; pass them as parameters.
- Never weaken the Bearer token check, the 500-character limit, the GET-only API, the exact-origin CORS list or the nginx log suppression.
- Never delete, skip or loosen a test, the evaluation baseline or an integrity check to make CI pass. Change `eval/baseline.json` or `eval/cases.jsonl` only in a reviewed, explained commit.
- Never hand-edit `api/data/medical.csv` to fix data; the importer quarantines bad fields and records why.
- Never run the live tests or the importer against a database that is not disposable or backed up; the live tests delete all data.
- Never force-push `main`, rewrite published history, overwrite a published release or image tag, or push a release tag unless the owner asks.
- Never touch the GitHub profile repository `hamza-aziz-ai/hamza-aziz-ai` or LinkedIn from this project.

## Always

- Always pin exact versions: Python and npm dependencies, Docker base images by digest, GitHub Actions by full commit SHA.
- Always log a new dependency in [DEPENDENCIES.md](DEPENDENCIES.md) with why it is needed and who maintains it, before adding it.
- Always draft a [DECISIONS.md](DECISIONS.md) entry before a non-trivial change, with the options considered.
- Always run the checks in [TESTING.md](TESTING.md) and report real output, not "tests pass".
- Always make one logical change per commit, with a message that says what changed and why.
- Always update [HANDOVER.md](HANDOVER.md) at the end of a session.

## Protected areas (pause and explain before changing)

- `api/main.py`: authentication, CORS, error handling, logging of requests.
- `api/build_medicalgraph.py`: ownership marker, refusal guards, snapshot replacement, quarantine rules.
- `scripts/evaluate_kg.py`, `eval/`: the MLOps gate.
- `.github/workflows/release.yml` and `automerge.yml`: publication and merging.
- `docker/nginx.conf`: request logging.

## AI allow policy (habit 22)

| Safe to allow                                                                                                                                                           | Pause and read                                                                                                                                                                         | Never auto-allow                                                                                                                                                                                                                  |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Reading files, searching, `graphify query`, running tests, linters and `actionlint`, formatting, edits on a feature branch, starting disposable Docker Neo4j containers | Edits across many files, workflow or Docker changes, adding a dependency, changing auth, CORS or logging, importer or data-quality rules, calls to a new external host, deleting files | Reading or editing `.env` or secrets, production or non-disposable databases, force-push or history rewrites, disabling tests or checks, `rm -rf`, piping downloads into a shell, publishing releases or tags without being asked |

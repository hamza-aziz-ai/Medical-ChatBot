# ASSUMPTIONS & OPEN QUESTIONS

What we are assuming but have not verified. Mark each verified, unverified or wrong. Clear or consciously accept the unverified items before anything ships to real users.

| ID | Assumption or question | Status | Notes |
|---|---|---|---|
| A-01 | `api/data/medical.csv` may be redistributed in a public repository | Unverified | Source and licence unknown; appears machine-translated from a Chinese medical KG (D30) |
| A-02 | `api/data/questions.json` (questiondoctors.com Q&A) may be redistributed | Unverified | Unused at runtime; kept as a historical record |
| A-03 | The project has no real users (Lane A) | Unverified | Based on the owner's description as a local student prototype; public images exist since v1.0.0 |
| A-04 | `['oncology', 'oncology']` means "oncology only" | Inference | Keeping the oncology link is correct under any reading |
| A-05 | One gunicorn worker is enough | Unverified | No load test; chosen because log rotation is per process |
| A-06 | Neo4j versions other than 5.26.32 and 4.4.48 work | Unverified | Only those two were tested |
| A-07 | The automerge path triggered by finished CI runs works | Unverified | The no-CI path merged PR #15; the CI path runs from the default branch and has not had a real PR yet |
| A-08 | MedlinePlus health-topic summaries are clinically reviewed | Unverified | Only NLM maintenance is documented |
| A-09 | A MedlinePlus + Disease Ontology composite would cover enough of the 658 diseases | Unmeasured | Needs the pilot in DECISIONS.md D-011 |
| A-10 | Answers are clinically accurate | Not established | Structural and source-faithfulness checks only; every answer carries "not medical advice" |
| A-11 | Hidden or third-party libraries never log questions | Verified for the app and proxy; partially for libraries | Smoke test checks container output and API logs for a sentinel question |

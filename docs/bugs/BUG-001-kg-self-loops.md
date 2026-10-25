# BUG-001: Self-links and a department cycle in the knowledge graph

**Symptom.** An integrity audit of a fresh import found 5 `accompany_with` relationships from a disease to itself and one `belongs_to` from the oncology department to itself, which formed the only cycle in the department hierarchy.

**Repro.** Import `api/data/medical.csv` at commit `6300fca` into a disposable Neo4j, then run `MATCH (a)-[r]->(a) RETURN type(r), a.name`.

**Root cause.** `graph_data()` added a complication link whenever the companion was a known disease, including the disease itself. It also read every two-element Cure Department list as `[parent, child]`, so `['oncology', 'oncology']` made oncology its own parent. A latent third problem: lists of more than two departments silently produced no department link.

**Fix.** Self-complications are skipped and reported; a repeated department counts once with no hierarchy link (14 rows); lists of more than two departments are quarantined for that disease; a hierarchy cycle stops the import before anything is written. `scripts/evaluate_kg.py` now checks the graph's invariants independently of the importer (PR #14).

**Verification.** 128 tests passed locally with live Neo4j, including planted corruptions that the checker catches; the real import passed the evaluation with 2,473 nodes and 5,301 relationships; CI passed on Neo4j 5 and 4.4.

## Log

- 2026-10-25: Found by the audit at `6300fca`; council with Codex agreed the fixes and the checker; merged as PR #14 (`3055257`).

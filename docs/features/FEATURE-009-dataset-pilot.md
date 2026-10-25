# FEATURE-009: Dataset pilot, step 1 (measurement)

**Goal.** Measure how many of our diseases MedlinePlus and the Disease Ontology name, before deciding anything about a sourced dataset (D-011, A-09).

**Scope.** `scripts/dataset_pilot.py`, `tests/test_dataset_pilot.py`, `docs/pilot/DATASET-PILOT.md`, `.gitignore` (`pilot-data/`), `backend.yml` (offline tests).

**Design.** Downloads only from two allow-listed URLs, with no redirects and a size cap; parses MedlinePlus XML with hardened stdlib Expat and the OBO file line by line; counts exact matches after NFKC, casefolding and whitespace collapsing. The aggregate report is committed; the per-disease mappings stay in `pilot-data/`.

**Status.** Measured: 207 of 658 diseases (31.5%) match in either source.

**Open questions.** Whether to fund a reviewed mapping of the 451 unmatched names; the rights and evaluation gates of D-011 still apply.

## Log

- 2026-10-26: Built and run after a council with Codex. Offline 281 passed, 11 skipped; live 292 passed.
- 2026-10-26: Step 2, a local candidate list for the 451 unmatched names (owner's choice; design agreed with Codex in council, 2 exchanges). `python scripts/dataset_pilot.py --candidates` reads only the cached files, recomputes the unmatched set with the step-1 method and leaves step 1's results alone. Five labelled lookups: punctuation relaxed, word order ignored (lossy), DOID RELATED/BROAD/NARROW synonyms (scope kept as DOID's), one leading qualifier removed (no relationship asserted), and a difflib fallback (ratio ≥ 0.88, top 3 concepts). Candidates are deduplicated by concept and keep every evidence path. Per-name candidates stay in git-ignored `pilot-data/candidates.json`; the report gains an aggregate-only section: 62 of 451 names have at least one candidate (27 by qualifier removal, 34 by similarity, 1 by punctuation), 389 have none; 28 s. Nothing is reviewed, applied or counted as coverage. Offline 302 passed, 12 skipped; live 314 passed.

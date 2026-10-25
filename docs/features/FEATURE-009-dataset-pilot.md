# FEATURE-009: Dataset pilot, step 1 (measurement)

**Goal.** Measure how many of our diseases MedlinePlus and the Disease Ontology name, before deciding anything about a sourced dataset (D-011, A-09).

**Scope.** `scripts/dataset_pilot.py`, `tests/test_dataset_pilot.py`, `docs/pilot/DATASET-PILOT.md`, `.gitignore` (`pilot-data/`), `backend.yml` (offline tests).

**Design.** Downloads only from two allow-listed URLs, with no redirects and a size cap; parses MedlinePlus XML with hardened stdlib Expat and the OBO file line by line; counts exact matches after NFKC, casefolding and whitespace collapsing. The aggregate report is committed; the per-disease mappings stay in `pilot-data/`.

**Status.** Measured: 207 of 658 diseases (31.5%) match in either source.

**Open questions.** Whether to fund a reviewed mapping of the 451 unmatched names; the rights and evaluation gates of D-011 still apply.

## Log

- 2026-10-26: Built and run after a council with Codex. Offline 281 passed, 11 skipped; live 292 passed.

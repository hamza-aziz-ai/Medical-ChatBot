# ALTERNATIVES

Options we turned down, what each would have cost, and what would change our mind. Linked to [DECISIONS.md](DECISIONS.md).

| Area | Rejected option | Why rejected | Revisit if |
|---|---|---|---|
| Answering (D-001) | Generative model | Can invent medical facts; not inspectable | Grounded generation with citations is evaluated and acceptable |
| Fallback (D-002) | Repair and retrain the Siamese-LSTM | Not reproducible (no seeded split or test set, needs Kaggle data and multi-GB GloVe); returns other patients' answers | A licensed, validated Q&A source and a real evaluation exist |
| Bad data (D-003) | Heuristic repair of malformed lists | Invents terms | Never for clinical facts |
| Bad data (D-003) | Refuse the whole import on one bad cell | One row blocks 650+ diseases | Errors become frequent enough to signal a broken source |
| Import (D-004) | `MERGE` upserts | Stale facts survive re-imports | Incremental updates are needed |
| Import (D-004) | Wipe the whole database | Destroys unrelated data | The database is dedicated and disposable |
| Access (D-005) | User accounts | Disproportionate for a local prototype | Real users (Lane B) |
| Frontend (D-006) | Keep a chat widget library on Vue 3 | Maintenance and accessibility unknown; extra dependency | The UI needs features the panel lacks |
| Frontend (D-006) | Drop linting | Loses an existing check | Never; lint is cheap |
| CI (D-007) | One orchestrator with custom change detection | Starts a run for docs-only changes; custom diff code to maintain | Required status checks are enabled |
| Delivery (D-007) | Deploy to a hosted server | No target, account or budget; putting a medical service online is the owner's call | The owner picks a host |
| Logs (D-008) | `error_log ... crit` | Severity filtering keeps request lines | Never |
| Integrity (D-009) | A separate integrity script | Duplicates the evaluator's driver, import and report | The checks outgrow the evaluator |
| Integrity (D-009) | Refuse lists of more than two departments | Blocks the whole import for one cell | Same as the bad-data rule above |
| Merging (D-010) | GitHub native auto-merge | Needs required checks, which path filters leave pending | Branch protection with a gate job |
| A-DATA (D-011) | SNOMED CT / UMLS | Redistribution only conditional; needs licensing work | A licence for a public snapshot |
| A-DATA (D-011) | SemMedDB | Needs credentials; final 2024 release; literature claims, not guidance | Never as a primary source |
| A-DATA (D-011) | HPO annotations as primary | Custom licence requiring unaltered content; negative annotations | Rare-disease scope with careful handling |
| A-DATA (D-011) | PrimeKG, Hetionet | Mostly molecular and drug data; Hetionet has 137 diseases | Research use, not patient-style Q&A |
| A-DATA (D-011) | Kaggle disease–symptom set | Provenance and clinical validation unknown | Never without provenance |
| A-DATA (D-011) | Original Chinese QASystemOnMedicalKG | Scraped, no open data licence; same lineage as the CSV | Never |
